import os
import sys
import json
import asyncio
import threading
import logging
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Ensure the backend directory is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Database functions
from db import (
    update_job, set_job_running, set_job_awaiting_approval,
    set_job_completed, set_job_failed
)

# Event bus
import event_bus as events

# Shared State
from api.state import (
    _plan_revisions, _direct_plan_updates, _worker_approval_events
)
from api.schemas import GenerationConfig

# Utilities
from api.utils import (
    get_job_healed, _get_job_lock, _update_metadata_json
)

logger = logging.getLogger("api.background")


def _get_pipeline_main():
    """Dynamically loads and caches the root main.py module safely."""
    if "backend_pipeline_main" in sys.modules and hasattr(sys.modules["backend_pipeline_main"], "save_blog_content"):
        return sys.modules["backend_pipeline_main"]
    import importlib.util
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    main_py_path = _BACKEND_DIR / "main.py"
    spec = importlib.util.spec_from_file_location("backend_pipeline_main", main_py_path)
    pipeline_main = importlib.util.module_from_spec(spec)
    sys.modules["backend_pipeline_main"] = pipeline_main
    try:
        spec.loader.exec_module(pipeline_main)
    except Exception:
        sys.modules.pop("backend_pipeline_main", None)
        raise
    return pipeline_main


def build_initial_state(job_id: str, topic: str, blog_folder: str,
                        generation_config: GenerationConfig) -> dict[str, Any]:
    """Assemble the graph's initial state from a validated GenerationConfig.

    Every key returned here must be declared in Graph.state.State — LangGraph
    drops undeclared keys silently. tests/test_state_schema.py enforces that.
    """
    from datetime import date
    return {
        "topic":             topic,
        "as_of":             date.today().isoformat(),
        "sections":          [],
        "blog_folder":       blog_folder,
        "target_tone":       generation_config.tone,
        "target_audience":   generation_config.audience,
        "target_keywords":   generation_config.keywords,
        "target_sections":   generation_config.sections,
        "generate_images":   generation_config.generate_images,
        "num_images":        generation_config.num_images,
        "generate_qa":       generation_config.generate_qa,
        "generate_campaign": generation_config.generate_campaign,
        "generate_video":    generation_config.generate_video,
        "generate_podcast":  generation_config.generate_podcast,
        "export_formats":    generation_config.export_formats,
        "_job_id":           job_id,
        # — Document upload —
        "upload_id":         generation_config.upload_id or "",
        "source_mode":       generation_config.source_mode,
        "selected_model":    generation_config.selected_model,
        "image_model":       generation_config.image_model,
        "image_size":        generation_config.image_size,
        "image_quality":     generation_config.image_quality,
        "image_style":       generation_config.image_style,
    }


def _create_sqlite_checkpoint_conn(checkpoints_db_path: Path):
    """Creates a thread-safe, high-concurrency SQLite connection for SqliteSaver."""
    import sqlite3
    conn = sqlite3.connect(str(checkpoints_db_path), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def _run_pipeline(
    job_id: str,
    topic: str,
    config: dict[str, Any],
    worker_event: threading.Event,
):
    """
    Runs the full LangGraph pipeline in a background thread.
    Emits events to the event_bus so the WebSocket can relay them.
    Supports persistent checkpointing via SqliteSaver, permitting
    seamless recovery and resumption after crashes/restarts.
    """
    conn = None
    try:
        generation_config = GenerationConfig.model_validate(config)
        # Late import so api.py can load without OPENAI_API_KEY set
        from dotenv import load_dotenv
        load_dotenv(_BACKEND_DIR.parent / ".env")

        import os as _os
        if not _os.getenv("OPENAI_API_KEY"):
            raise EnvironmentError("OPENAI_API_KEY not set in .env")

        # ── Import pipeline pieces ────────────────────────────────────────
        pipeline_main = _get_pipeline_main()
        build_graph = pipeline_main.build_graph
        create_blog_structure = pipeline_main.create_blog_structure
        save_blog_content = pipeline_main.save_blog_content
        generate_readme = pipeline_main.generate_readme
        refine_plan_with_llm = pipeline_main.refine_plan_with_llm
        from datetime import date
        db_url = _os.getenv("DATABASE_URL")
        if db_url and (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                from psycopg_pool import ConnectionPool
                pool = ConnectionPool(conninfo=db_url, max_size=20)
                memory = PostgresSaver(pool)
                memory.setup()
            except Exception as pg_err:
                logger.warning(f"PostgresSaver init failed ({pg_err}), falling back to SqliteSaver")
                from langgraph.checkpoint.sqlite import SqliteSaver
                checkpoints_db = _BACKEND_DIR / "data" / "checkpoints.db"
                checkpoints_db.parent.mkdir(exist_ok=True)
                conn = _create_sqlite_checkpoint_conn(checkpoints_db)
                memory = SqliteSaver(conn)
                memory.setup()
        else:
            from langgraph.checkpoint.sqlite import SqliteSaver
            checkpoints_db = _BACKEND_DIR / "data" / "checkpoints.db"
            checkpoints_db.parent.mkdir(exist_ok=True)
            conn = _create_sqlite_checkpoint_conn(checkpoints_db)
            memory = SqliteSaver(conn)
            memory.setup()

        # ── Build graph ───────────────────────────────────────────────────
        graph = build_graph(memory=memory)
        # Use job_id as the stable thread identifier
        thread_cfg = {"configurable": {"thread_id": job_id}}

        # ── Resume Detection & State Setup ───────────────────────────────
        state = graph.get_state(thread_cfg)
        is_resume = bool(state.next)

        if is_resume:
            job_data = get_job_healed(job_id)
            if job_data and job_data.get("blog_folder"):
                base_folder = job_data["blog_folder"]
                folders = {
                    "base":     base_folder,
                    "content":  f"{base_folder}/content",
                    "social":   f"{base_folder}/social_media",
                    "reports":  f"{base_folder}/reports",
                    "assets":   f"{base_folder}/assets/images",
                    "research": f"{base_folder}/research",
                    "audio":    f"{base_folder}/audio",
                    "video":    f"{base_folder}/video",
                    "metadata": f"{base_folder}/metadata"
                }
            else:
                # Fallback if DB didn't have it saved
                folders = create_blog_structure(topic)
                set_job_running(job_id, folders["base"])

            events.emit(job_id, "system", "resumed",
                        f"Resuming blog generation for: {topic}", {"blog_folder": folders["base"]})
        else:
            # ── Folder structure ──────────────────────────────────────────────
            folders = create_blog_structure(topic)
            set_job_running(job_id, folders["base"])

            events.emit(job_id, "system", "started",
                        f"Pipeline started for: {topic}", {"blog_folder": folders["base"]})

        initial_state = build_initial_state(
            job_id, topic, folders["base"], generation_config
        )

        # ── Phase 1: Research & Planning ─────────────────────────────────────
        current_job = get_job_healed(job_id)
        # Only treat as already approved if resuming an existing thread that was already approved past orchestrator
        already_approved = is_resume and bool(current_job and current_job.get("status") == "running" and state and state.next != ('orchestrator',))

        state = graph.get_state(thread_cfg)
        plan  = state.values.get("plan") if state else None

        if not plan:
            events.emit(job_id, "router", "working", "Analyzing topic and routing to agents...")
            for _ in graph.stream(initial_state if not is_resume else None, thread_cfg, stream_mode="values"):
                pass
            state = graph.get_state(thread_cfg)
            plan  = state.values.get("plan")

        if plan and not already_approved:
            plan_dict = plan.model_dump()
            set_job_awaiting_approval(job_id, json.dumps(plan_dict))
            events.emit(job_id, "orchestrator", "plan_ready",
                        "Blog plan ready for approval.", {"plan": plan_dict})

            # Wait for user approval (up to 20 minutes)
            worker_event.clear()
            logger.info(f"⏳ Job {job_id}: Awaiting HITL plan approval...")
            approved = worker_event.wait(timeout=1200)
            if not approved:
                logger.error(f"❌ Job {job_id}: Plan approval timed out after 20 minutes.")
                raise TimeoutError("HITL plan approval timed out")

            # Apply direct plan edit or LLM-based revision
            from Graph.agents.orchestrator import _assign_evidence_to_tasks
            evidence = state.values.get("evidence", [])

            direct_plan = _direct_plan_updates.pop(job_id, None)
            revised = _plan_revisions.pop(job_id, None)

            if direct_plan is not None:
                # User directly edited the outline — use their plan as-is
                new_plan = direct_plan
                if evidence:
                    new_plan = _assign_evidence_to_tasks(new_plan, evidence)
                graph.update_state(thread_cfg, {"plan": new_plan})
                # Update the stored plan in DB so frontend stays in sync
                set_job_awaiting_approval(job_id, json.dumps(new_plan.model_dump()))
                events.emit(job_id, "orchestrator", "plan_revised",
                            "Plan updated with your direct edits.")
            elif revised is not None:
                new_plan = refine_plan_with_llm(plan, revised)
                if evidence:
                    new_plan = _assign_evidence_to_tasks(new_plan, evidence)
                graph.update_state(thread_cfg, {"plan": new_plan})
                events.emit(job_id, "orchestrator", "plan_revised",
                            "Plan updated based on your feedback.")

            update_job(job_id, status="running")
            events.emit(job_id, "orchestrator", "plan_approved", "Plan approved. Starting writing phase...")
        elif plan:
            events.emit(job_id, "orchestrator", "plan_approved", "Plan already approved. Resuming writing phase...")

        # ── Phase 2: Write & Produce ──────────────────────────────────────
        events.emit(job_id, "writer", "working", "Writing blog sections...")
        for _ in graph.stream(None, thread_cfg, stream_mode="values", recursion_limit=150):
            pass

        # ── Save outputs ──────────────────────────────────────────────────
        final_state = graph.get_state(thread_cfg).values
        saved       = save_blog_content(folders, final_state)
        generate_readme(folders, saved, final_state)

        # Read the blog content for serving via API
        final_content = final_state.get("final", "")
        
        # We store relative paths in the DB to work with the /api/files endpoint
        blog_relative = os.path.relpath(saved["blog"], folders["base"]) if saved.get("blog") else None
        html_relative = os.path.relpath(saved["blog_html"], folders["base"]) if saved.get("blog_html") else None
        podcast_relative = os.path.relpath(saved["podcast"], folders["base"]) if saved.get("podcast") else None
        video_relative = os.path.relpath(saved["video"], folders["base"]) if saved.get("video") else None

        set_job_completed(
            job_id,
            qa_score             = final_state.get("qa_score"),
            qa_verdict           = final_state.get("qa_verdict"),
            blog_evaluator_score = final_state.get("blog_evaluator_score"),
            geval_scores         = final_state.get("geval_scores"),
            deepeval_scores      = final_state.get("deepeval_scores"),
            blog_file            = blog_relative,
            blog_html_file       = html_relative,
            podcast_file         = podcast_relative,
            video_file           = video_relative,
            word_count           = len(final_content.split()),
            final_content        = final_content,
            social_linkedin      = final_state.get("linkedin_post", ""),
            social_twitter       = final_state.get("twitter_thread", ""),
        )

        events.emit(job_id, "system", "completed",
                    "Blog generation complete!",
                    {
                        "qa_score": final_state.get("qa_score"),
                        "blog_evaluator_score": final_state.get("blog_evaluator_score"),
                        "geval_scores": final_state.get("geval_scores"),
                        "deepeval_scores": final_state.get("deepeval_scores"),
                        "blog_folder": folders["base"],
                    })

    except Exception as exc:
        logger.exception(f"Pipeline failed for job {job_id}: {exc}")
        set_job_failed(job_id, str(exc))
        events.emit(job_id, "system", "error", f"Generation failed: {exc}")
    finally:
        if conn:
            conn.close()
        _worker_approval_events.pop(job_id, None)


def _run_manual_task(job_id: str, task_name: str):
    """Runs a specific decoupled media or QA task on a completed blog."""
    if not events.register_active_task(job_id, task_name):
        logger.warning(f"Task '{task_name}' for job {job_id} is already running. Skipping duplicate request.")
        return
    try:
        _run_manual_task_inner(job_id, task_name)
    finally:
        events.unregister_active_task(job_id, task_name)


def _run_manual_task_inner(job_id: str, task_name: str):
    """Delegate post-generation work to focused task handlers."""
    from api.manual_tasks import run_manual_task

    run_manual_task(
        job_id,
        task_name,
        backend_dir=_BACKEND_DIR,
        pipeline_loader=_get_pipeline_main,
    )


def _ensure_pipeline_running(job_id: str):
    """
    If the worker thread is currently active, unblock it.
    If the worker thread was lost (e.g. server restarted), start a new one in resume mode.
    """
    worker_event = _worker_approval_events.get(job_id)
    if worker_event:
        worker_event.set()
        logger.info(f"Set worker approval event for active job {job_id}")
    else:
        # Re-trigger pipeline execution in resume mode
        job = get_job_healed(job_id)
        if not job:
            logger.error(f"Cannot resume job {job_id}: job not found in DB.")
            return

        new_event = threading.Event()
        new_event.set() # Unblock immediately
        _worker_approval_events[job_id] = new_event
        generation_config = job.get("config", {})

        t = threading.Thread(
            target=_run_pipeline,
            kwargs={
                "job_id":            job_id,
                "topic":             job["topic"],
                "config":            generation_config,
                "worker_event":      new_event,
            }
        )
        t.daemon = True
        t.start()
        logger.info(f"🚀 Re-spawned background pipeline thread to resume job {job_id}")
