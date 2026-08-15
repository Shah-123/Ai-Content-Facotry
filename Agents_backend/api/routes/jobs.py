import os
import re
import json
import logging
import asyncio
import tempfile
import threading
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from db import create_job, get_job, update_job, delete_job
from api.schemas import CreateJobRequest, RevisePlanRequest, UpdatePlanRequest
from api.state import _worker_approval_events, _plan_revisions, _direct_plan_updates
from api.utils import get_job_healed, list_jobs_healed
from api.background import _run_pipeline, _run_manual_task, _ensure_pipeline_running

logger = logging.getLogger("api.routes.jobs")
router = APIRouter(tags=["jobs"])


@router.post("/api/jobs")
async def create_new_job(req: CreateJobRequest, background_tasks: BackgroundTasks):
    """Start a blog generation job."""
    # ── Pre-flight Topic Guard ────────────────────────────────────────────
    # Reject unsafe / nonsensical topics BEFORE creating a job or burning
    # any pipeline tokens. Run in a worker thread so the synchronous LLM
    # call doesn't block the FastAPI event loop.
    from Graph.agents.topic_guard import evaluate_topic
    verdict = await asyncio.to_thread(evaluate_topic, req.topic)
    if not verdict.is_safe:
        logger.warning(
            f"Topic rejected by guard: '{req.topic[:80]}' "
            f"(category={verdict.category}) — {verdict.reason}"
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "topic_rejected",
                "category": verdict.category,
                "reason": verdict.reason,
                "suggested_topic": verdict.suggested_topic,
            },
        )

    generation_config = req.model_dump(exclude={"topic"}, mode="json")
    job = await asyncio.to_thread(create_job, topic=req.topic, config=generation_config)
    job_id = job["id"]

    # Create threading.Event for HITL synchronisation with the worker thread
    worker_event = threading.Event()
    _worker_approval_events[job_id] = worker_event

    background_tasks.add_task(
        _run_pipeline,
        job_id            = job_id,
        topic             = req.topic,
        config            = generation_config,
        worker_event      = worker_event,
    )
    return job


@router.get("/api/jobs")
async def list_all_jobs():
    """Return all jobs, newest-first."""
    return await asyncio.to_thread(list_jobs_healed)


@router.get("/api/jobs/{job_id}")
async def get_job_details(job_id: str):
    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/api/jobs/{job_id}/events")
async def get_job_events(job_id: str):
    """Return all historical events emitted for this job."""
    from event_bus import _heal_stuck_events
    events_list = await asyncio.to_thread(_heal_stuck_events, job_id)
    return {"events": events_list}


@router.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    job = await asyncio.to_thread(get_job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Clean up files on disk if the folder exists
    blog_folder = job.get("blog_folder")
    if blog_folder and os.path.exists(blog_folder):
        import shutil
        try:
            await asyncio.to_thread(shutil.rmtree, blog_folder)
            logger.info(f"Deleted blog folder: {blog_folder}")
        except Exception as e:
            logger.error(f"Failed to delete blog folder {blog_folder}: {e}")
            
    # Delete from database
    deleted = await asyncio.to_thread(delete_job, job_id)
    if not deleted:
        raise HTTPException(500, "Failed to delete job from database")
        
    return {"status": "success", "message": f"Job {job_id} deleted successfully"}


@router.get("/api/jobs/{job_id}/blog")
async def get_blog_content(job_id: str):
    """Return the raw markdown blog content."""
    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    content = job.get("final_content") or ""
    if not content and job.get("blog_file") and job.get("blog_folder"):
        try:
            blog_path = Path(job["blog_folder"]) / job["blog_file"]
            content = await asyncio.to_thread(blog_path.read_text, encoding="utf-8")
        except Exception:
            pass
    return {"content": content, "format": "markdown"}


@router.get("/api/jobs/{job_id}/export/html")
async def export_html(job_id: str):
    """Export the blog post as a styled HTML file with embedded pictures."""
    from fastapi.responses import Response
    from exporters import export_to_html

    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    content = job.get("final_content") or ""
    title = job.get("topic") or "blog_post"
    blog_folder = job.get("blog_folder")
    job_dir = Path(blog_folder) if blog_folder else None

    html_code = export_to_html(title, content, job_dir=job_dir)
    filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', title)[:40]}.html"
    return Response(
        content=html_code,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/jobs/{job_id}/export/docx")
async def export_docx(job_id: str):
    """Export the blog post as a Microsoft Word (.docx) file with embedded pictures."""
    from exporters import export_to_docx

    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    content = job.get("final_content") or ""
    title = job.get("topic") or "blog_post"
    blog_folder = job.get("blog_folder") or tempfile.gettempdir()
    job_dir = Path(blog_folder)

    export_path = job_dir / "exports" / f"{re.sub(r'[^a-zA-Z0-9]', '_', title)[:40]}.docx"
    await asyncio.to_thread(export_to_docx, title, content, export_path, job_dir=job_dir)

    return FileResponse(
        path=str(export_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=export_path.name
    )


@router.get("/api/jobs/{job_id}/export/pdf")
async def export_pdf(job_id: str):
    """Export the blog post as a PDF file with embedded pictures."""
    from exporters import export_to_pdf

    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    content = job.get("final_content") or ""
    title = job.get("topic") or "blog_post"
    blog_folder = job.get("blog_folder") or tempfile.gettempdir()
    job_dir = Path(blog_folder)

    export_path = job_dir / "exports" / f"{re.sub(r'[^a-zA-Z0-9]', '_', title)[:40]}.pdf"
    await asyncio.to_thread(export_to_pdf, title, content, export_path, job_dir=job_dir)

    return FileResponse(
        path=str(export_path),
        media_type="application/pdf",
        filename=export_path.name
    )


@router.get("/api/jobs/{job_id}/approve-plan")
async def approve_plan(job_id: str):
    """Signal HITL approval — unblocks the worker thread."""
    job = await asyncio.to_thread(get_job_healed, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    _plan_revisions[job_id] = None  # no revision — straight approve
    _ensure_pipeline_running(job_id)
    await asyncio.to_thread(update_job, job_id, status="running")
    return {"status": "approved"}


@router.post("/api/jobs/{job_id}/revise-plan")
async def revise_plan(job_id: str, req: RevisePlanRequest):
    """Submit feedback and unblock the worker to apply revision."""
    job = get_job_healed(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    _plan_revisions[job_id] = req.feedback
    _ensure_pipeline_running(job_id)
    update_job(job_id, status="running")
    return {"status": "revision_queued"}


@router.post("/api/jobs/{job_id}/update-plan")
async def update_plan_direct(job_id: str, req: UpdatePlanRequest):
    """Accept a directly-edited plan from the frontend outline editor and unblock the worker."""
    from Graph.state import Plan, Task

    job = get_job_healed(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Rebuild Task list with sequential IDs and safe defaults
    tasks = []
    for i, t in enumerate(req.tasks):
        tasks.append(Task(
            id=i,
            title=t.get("title", f"Section {i + 1}"),
            goal=t.get("goal", ""),
            bullets=t.get("bullets", []),
            target_words=t.get("target_words", 350),
            tags=t.get("tags", []),
            assigned_evidence_indices=[],  # will be re-assigned by the worker thread
        ))

    new_plan = Plan(
        blog_title=req.blog_title,
        tone=req.tone,
        audience=req.audience,
        tasks=tasks,
        primary_keywords=job.get("plan", {}).get("primary_keywords", []) if job.get("plan") else [],
        keyword_strategy=job.get("plan", {}).get("keyword_strategy", "") if job.get("plan") else "",
    )

    _direct_plan_updates[job_id] = new_plan
    _ensure_pipeline_running(job_id)
    updated_config = {**job.get("config", {}), "tone": req.tone, "audience": req.audience}
    update_job(job_id, status="running", tone=req.tone, config_json=updated_config)
    return {"status": "plan_updated", "sections": len(tasks)}


@router.post("/api/jobs/{job_id}/resume")
async def resume_job_endpoint(job_id: str):
    """Manually resumes a failed or halted job from its last persisted checkpoint."""
    job = get_job_healed(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    update_job(job_id, status="running")
    _ensure_pipeline_running(job_id)
    return {"status": "resumed", "job_id": job_id}


@router.get("/api/jobs/{job_id}/qa-report")
async def get_qa_report(job_id: str):
    """Return the QA report text for a completed job."""
    job = get_job_healed(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    report_text = ""
    if job.get("blog_folder"):
        report_path = Path(job["blog_folder"]) / "reports" / "qa_report.txt"
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")
    return {"report": report_text}


@router.get("/api/files/{job_id}/{filepath:path}")
async def serve_file(job_id: str, filepath: str):
    """Serve any file from a job's blog folder."""
    job = get_job_healed(job_id)
    if not job or not job.get("blog_folder"):
        raise HTTPException(404, "Job not found")
    base = Path(job["blog_folder"]).resolve()
    full_path = (base / filepath).resolve()
    # Containment check, NOT a string prefix check: `startswith` let a job whose
    # folder is `blogs/topic_123` read `blogs/topic_1234/...` via `../`.
    if not full_path.is_relative_to(base):
        raise HTTPException(403, "Invalid path")
    if not full_path.exists():
        raise HTTPException(404, f"File not found: {filepath}")
    return FileResponse(str(full_path))


@router.post("/api/jobs/{job_id}/generate-images")
async def manual_images(job_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_manual_task, job_id, "images")
    return {"status": "started", "task": "images"}


@router.post("/api/jobs/{job_id}/generate-video")
async def manual_video(job_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_manual_task, job_id, "video")
    return {"status": "started", "task": "video"}


@router.post("/api/jobs/{job_id}/generate-podcast")
async def manual_podcast(job_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_manual_task, job_id, "podcast")
    return {"status": "started", "task": "podcast"}


@router.post("/api/jobs/{job_id}/generate-social")
async def manual_social(job_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_manual_task, job_id, "campaign")
    return {"status": "started", "task": "campaign"}


@router.post("/api/jobs/{job_id}/run-qa")
async def manual_qa(job_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_manual_task, job_id, "qa")
    return {"status": "started", "task": "qa"}


@router.post("/api/jobs/{job_id}/run-deepeval")
async def manual_deepeval(job_id: str, background_tasks: BackgroundTasks):
    """Trigger the official deepeval G-Eval audit (Liu et al. 2023) on demand.
    Runs 4 LLM calls (one per rubric) and writes results to the deepeval_scores
    column, metadata.json, and reports/deepeval_report.txt.
    """
    background_tasks.add_task(_run_manual_task, job_id, "deepeval")
    return {"status": "started", "task": "deepeval"}
