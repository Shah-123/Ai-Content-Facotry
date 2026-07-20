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

# Utilities
from api.utils import (
    get_job_healed, _get_job_lock, _update_metadata_json
)

logger = logging.getLogger("api.background")


def _run_pipeline(job_id: str, topic: str, tone: str, audience: str,
                  sections: int, generate_podcast: bool, generate_video: bool,
                  generate_campaign: bool, generate_qa: bool,
                  worker_event: threading.Event,
                  keywords: list[str] | None = None,
                  upload_id: str | None = None,
                  source_mode: str = "hybrid"):
    """
    Runs the full LangGraph pipeline in a background thread.
    Emits events to the event_bus so the WebSocket can relay them.
    Supports persistent checkpointing via SqliteSaver, permitting
    seamless recovery and resumption after crashes/restarts.
    """
    conn = None
    try:
        # Late import so api.py can load without OPENAI_API_KEY set
        from dotenv import load_dotenv
        load_dotenv(_BACKEND_DIR / ".env")

        import os as _os
        if not _os.getenv("OPENAI_API_KEY"):
            raise EnvironmentError("OPENAI_API_KEY not set in .env")

        # ── Import pipeline pieces ────────────────────────────────────────
        from main import (
            build_graph, create_blog_structure, save_blog_content,
            generate_readme, refine_plan_with_llm
        )
        from datetime import date
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver

        # ── Initialize SQLite Checkpointer ────────────────────────────────
        checkpoints_db = _BACKEND_DIR / "data" / "checkpoints.db"
        checkpoints_db.parent.mkdir(exist_ok=True)
        
        conn = sqlite3.connect(str(checkpoints_db), check_same_thread=False)
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

        initial_state = {
            "topic":             topic,
            "as_of":             date.today().isoformat(),
            "sections":          [],
            "blog_folder":       folders["base"],
            "target_tone":       tone,
            "target_audience":   audience,
            "target_keywords":   list(keywords or []),
            "target_sections":   sections,
            "generate_images":   False,
            "generate_qa":       generate_qa,
            "generate_campaign": generate_campaign,
            "generate_video":    generate_video,
            "generate_podcast":  generate_podcast,
            "export_formats":    ["html"],
            "_job_id":           job_id,
            # — Document upload —
            "upload_id":         upload_id or "",
            "source_mode":       source_mode,
        }

        # ── Phase 1: Research & Planning (Skip if resuming) ─────────────────
        if not is_resume:
            events.emit(job_id, "router", "working", "Analyzing topic and routing to agents...")
            for _ in graph.stream(initial_state, thread_cfg, stream_mode="values"):
                pass

            # ── HITL: surface the plan to the frontend ────────────────────────
            state = graph.get_state(thread_cfg)
            plan  = state.values.get("plan")
            if plan:
                plan_dict = plan.model_dump()
                set_job_awaiting_approval(job_id, json.dumps(plan_dict))
                events.emit(job_id, "orchestrator", "plan_ready",
                            "Blog plan ready for approval.", {"plan": plan_dict})

                # Wait for user approval (up to 20 minutes)
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
                    # ✅ FIX: Re-assign evidence to the revised plan's tasks
                    if evidence:
                        new_plan = _assign_evidence_to_tasks(new_plan, evidence)
                    graph.update_state(thread_cfg, {"plan": new_plan})
                    events.emit(job_id, "orchestrator", "plan_revised",
                                "Plan updated based on your feedback.")

                events.emit(job_id, "orchestrator", "plan_approved", "Plan approved. Starting writing phase...")
        else:
            # ── Resuming after crash/restart (Phase 1 was already run) ────
            state = graph.get_state(thread_cfg)
            plan  = state.values.get("plan")
            evidence = state.values.get("evidence", [])

            direct_plan = _direct_plan_updates.pop(job_id, None)
            revised = _plan_revisions.pop(job_id, None)

            if direct_plan is not None:
                from Graph.agents.orchestrator import _assign_evidence_to_tasks
                new_plan = direct_plan
                if evidence:
                    new_plan = _assign_evidence_to_tasks(new_plan, evidence)
                graph.update_state(thread_cfg, {"plan": new_plan})
                set_job_awaiting_approval(job_id, json.dumps(new_plan.model_dump()))
                events.emit(job_id, "orchestrator", "plan_revised",
                            "Plan updated with your direct edits.")
            elif revised is not None:
                from Graph.agents.orchestrator import _assign_evidence_to_tasks
                new_plan = refine_plan_with_llm(plan, revised)
                if evidence:
                    new_plan = _assign_evidence_to_tasks(new_plan, evidence)
                graph.update_state(thread_cfg, {"plan": new_plan})
                events.emit(job_id, "orchestrator", "plan_revised",
                            "Plan updated based on your feedback.")

            events.emit(job_id, "orchestrator", "plan_approved", "Plan approved. Starting writing phase...")

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
    """Runs a specific decoupled media or QA task on a completed blog.

    Media tasks (video, podcast, campaign) save ONLY their own artifact
    and do a surgical DB + metadata update — they never call the heavy
    save_blog_content() function. This makes them safe to run in parallel.

    Content-modifying tasks (images, qa) still use save_blog_content()
    because they rewrite the blog markdown, but they acquire a per-job
    file lock to prevent concurrent metadata corruption.
    """
    events.register_active_task(job_id, task_name)
    try:
        _run_manual_task_inner(job_id, task_name)
    finally:
        events.unregister_active_task(job_id, task_name)


def _run_manual_task_inner(job_id: str, task_name: str):
    try:
        from dotenv import load_dotenv
        load_dotenv(_BACKEND_DIR / ".env")

        from Graph.nodes import (
            decide_images, generate_and_place_images,
            video_generator_node, podcast_node,
            campaign_generator_node, qa_agent_node,
            revision_node, deepeval_evaluation_node
        )

        job = get_job_healed(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        base_path = job["blog_folder"]
        meta_path = Path(base_path) / "metadata" / "metadata.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        blog_path_str = meta.get("file_paths", {}).get("blog")
        if blog_path_str and Path(blog_path_str).exists():
            blog_path = Path(blog_path_str)
        else:
            content_dir = Path(base_path) / "content"
            md_files = list(content_dir.glob("*.md")) if content_dir.exists() else []
            if md_files:
                blog_path = md_files[0]
            else:
                md_files = list(Path(base_path).glob("*.md"))
                if md_files:
                    blog_path = md_files[0]
                else:
                    raise FileNotFoundError(f"Could not locate blog markdown file in {base_path}")

        with open(blog_path, "r", encoding="utf-8") as f:
            final_md = f.read()

        from Graph.state import Plan
        plan_path = Path(base_path) / "metadata" / "plan.json"
        plan_obj = None
        if plan_path.exists():
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
                plan_obj = Plan(**plan_data)

        state = {
            "topic": meta.get("topic", "Unknown"),
            "target_tone": meta.get("target_tone", "professional"),
            "target_keywords": meta.get("target_keywords", []),
            "merged_md": final_md,
            "final": final_md,
            "blog_folder": base_path,
            "_job_id": job_id,
            "qa_verdict": meta.get("qa_verdict", "READY"),
            "qa_score": meta.get("qa_score", 0),
            "qa_issues": [],
            "revision_count": 0,
            "qa_fixed_claims": [],
            "plan": plan_obj
        }

        events.emit(job_id, task_name, "started", f"Starting manual {task_name}...")

        job_lock = _get_job_lock(job_id)

        # ── Ensure output directories exist ─────────────────────────────
        for sub in ("content", "social_media", "reports", "assets/images",
                     "research", "audio", "video", "metadata"):
            os.makedirs(Path(base_path) / sub, exist_ok=True)

        # ==================================================================
        # MEDIA TASKS — lightweight, concurrency-safe, no save_blog_content
        # ==================================================================

        if task_name == "video":
            video_out = Path(base_path) / "video" / "short.mp4"
            if video_out.exists() and video_out.stat().st_size > 0:
                events.emit(job_id, task_name, "completed", "Video already exists. Skipping.")
                if not job.get("video_file"):
                    update_job(job_id, video_file="video/short.mp4")
                return
            state.update(video_generator_node(state))
            # Save the video file to the correct location
            import shutil
            copied = False
            if state.get("video_path") and os.path.exists(state["video_path"]) and os.path.getsize(state["video_path"]) > 0:
                dest = str(video_out)
                try:
                    if not os.path.samefile(state["video_path"], dest):
                        shutil.copy(state["video_path"], dest)
                except (OSError, ValueError):
                    shutil.copy(state["video_path"], dest)
                if video_out.exists() and video_out.stat().st_size > 0:
                    copied = True

            if copied:
                # Surgical DB update — only touch the video column
                rel = "video/short.mp4"
                update_job(job_id, video_file=rel)
                _update_metadata_json(meta_path, {"file_paths": {"video": str(video_out)}}, job_lock)
                events.emit(job_id, "system", "completed", "Video completed successfully.")
            else:
                raise RuntimeError("Video file generation or saving failed (output file is missing or empty).")
            return

        if task_name == "podcast":
            podcast_out = Path(base_path) / "audio" / "podcast.wav"
            podcast_mp3 = Path(base_path) / "audio" / "podcast.mp3"
            
            valid_existing = None
            if podcast_mp3.exists() and podcast_mp3.stat().st_size > 0:
                valid_existing = "audio/podcast.mp3"
            elif podcast_out.exists() and podcast_out.stat().st_size > 0:
                valid_existing = "audio/podcast.wav"

            if valid_existing:
                events.emit(job_id, task_name, "completed", "Podcast already exists. Skipping.")
                if not job.get("podcast_file"):
                    update_job(job_id, podcast_file=valid_existing)
                return
            state.update(podcast_node(state))
            # Save the podcast file to the correct location
            import shutil
            copied = False
            src_path = state.get("podcast_audio_path")
            if src_path and os.path.exists(src_path) and os.path.getsize(src_path) > 0:
                ext = Path(src_path).suffix.lower()
                if ext == ".mp3":
                    dest_file = podcast_mp3
                    rel_path = "audio/podcast.mp3"
                else:
                    dest_file = podcast_out
                    rel_path = "audio/podcast.wav"
                    
                dest = str(dest_file)
                try:
                    if not os.path.samefile(src_path, dest):
                        shutil.copy(src_path, dest)
                except (OSError, ValueError):
                    shutil.copy(src_path, dest)
                if dest_file.exists() and dest_file.stat().st_size > 0:
                    copied = True

            if copied:
                # Surgical DB update — only touch the podcast column
                update_job(job_id, podcast_file=rel_path)
                _update_metadata_json(meta_path, {"file_paths": {"podcast": str(dest_file)}}, job_lock)
                events.emit(job_id, "system", "completed", "Podcast completed successfully.")
            else:
                raise RuntimeError("Podcast file generation or saving failed (output file is missing or empty).")
            return

        if task_name == "deepeval":
            # Load research evidence from disk so the accuracy/grounding
            # rubric has retrieval_context to check against.
            evidence_path = Path(base_path) / "research" / "evidence.json"
            if evidence_path.exists():
                try:
                    with open(evidence_path, "r", encoding="utf-8") as ef:
                        state["evidence"] = json.load(ef)
                except Exception as ev_err:
                    logger.warning(f"Could not load evidence.json: {ev_err}")
                    state["evidence"] = []
            else:
                state["evidence"] = []

            result = deepeval_evaluation_node(state)
            deepeval_scores = result.get("deepeval_scores")
            if deepeval_scores:
                # Persist to DB
                update_job(job_id, deepeval_scores=deepeval_scores)

                # Write deepeval_report.txt
                try:
                    report_path = Path(base_path) / "reports" / "deepeval_report.txt"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    lines = [
                        "DEEPEVAL G-EVAL REPORT (Liu et al. 2023)",
                        "=" * 60,
                        "Library:        deepeval (official implementation)",
                        "Score Scale:    0.0 (worst) - 1.0 (best)",
                        f"Overall Score:  {deepeval_scores.get('overall_score', 'N/A')}/1.0",
                        "",
                        "Rubric Evaluations:",
                        "-" * 60,
                    ]
                    rubric_labels = {
                        "coherence": "1. COHERENCE",
                        "relevance": "2. RELEVANCE",
                        "accuracy": "3. ACCURACY & GROUNDING",
                        "tone_alignment": "4. TONE ALIGNMENT",
                    }
                    for key, label in rubric_labels.items():
                        criterion = deepeval_scores.get(key) or {}
                        lines.append(f"{label}: {criterion.get('score', 'N/A')}/1.0")
                        lines.append(f"   Reasoning: {criterion.get('reasoning', 'N/A')}")
                        lines.append("")
                    report_path.write_text("\n".join(lines), encoding="utf-8")
                except Exception as report_err:
                    logger.warning(f"Could not write deepeval_report.txt: {report_err}")

                # Update metadata.json
                _update_metadata_json(meta_path, {"deepeval_scores": deepeval_scores}, job_lock)

                events.emit(job_id, "system", "completed",
                            "Academic audit (deepeval G-Eval) completed.",
                            {"deepeval_scores": deepeval_scores})
            else:
                events.emit(job_id, "system", "error",
                            "Academic audit failed — no scores returned. Is deepeval installed?")
            return

        if task_name == "campaign":
            if job.get("social_linkedin") or job.get("social_twitter"):
                events.emit(job_id, task_name, "completed", "Social media already exists. Skipping.")
                return
            state.update(campaign_generator_node(state))
            # Save social media text files
            slug = plan_obj.blog_title.replace(" ", "_").lower()[:50] if plan_obj else "blog"
            social_dir = Path(base_path) / "social_media"
            if state.get("linkedin_post"):
                (social_dir / f"linkedin_{slug}.txt").write_text(state["linkedin_post"], encoding="utf-8")
            if state.get("twitter_thread"):
                (social_dir / f"twitter_{slug}.md").write_text(state["twitter_thread"], encoding="utf-8")
            # Surgical DB update — only touch social columns
            update_job(
                job_id,
                social_linkedin=state.get("linkedin_post", ""),
                social_twitter=state.get("twitter_thread", ""),
            )
            events.emit(job_id, "system", "completed", "Campaign completed successfully.")
            return

        # ==================================================================
        # CONTENT-MODIFYING TASKS — use save_blog_content with file lock
        # ==================================================================

        from main import save_blog_content

        updates = {}

        if task_name == "images":
            state.update(decide_images(state))
            state.update(generate_and_place_images(state))

        elif task_name == "qa":
            state.update(qa_agent_node(state))
            if state.get("qa_verdict") == "NEEDS_REVISION":
                state.update(revision_node(state))
                state.update(qa_agent_node(state))
            updates["qa_score"] = state.get("qa_score")
            updates["qa_verdict"] = state.get("qa_verdict")
            updates["final_content"] = state.get("final")

        # Build folders dict for save_blog_content
        folders = {
            "base": base_path,
            "content": f"{base_path}/content",
            "social": f"{base_path}/social_media",
            "reports": f"{base_path}/reports",
            "assets": f"{base_path}/assets/images",
            "research": f"{base_path}/research",
            "audio": f"{base_path}/audio",
            "video": f"{base_path}/video",
            "metadata": f"{base_path}/metadata"
        }

        saved = {}
        with job_lock:
            try:
                saved = save_blog_content(folders, state)
            except Exception as save_err:
                logger.warning(f"save_blog_content failed ({save_err}), falling back to direct DB update")

        if saved.get("blog"):
            updates["blog_file"] = os.path.relpath(saved["blog"], base_path)
        if saved.get("blog_html"):
            updates["blog_html_file"] = os.path.relpath(saved["blog_html"], base_path)
        if task_name == "images" and "final" in state:
            updates["final_content"] = state["final"]

        if updates:
            update_job(job_id, **updates)

        events.emit(job_id, "system", "completed", f"{task_name.capitalize()} completed successfully.")

    except Exception as exc:
        logger.exception(f"Manual {task_name} failed: {exc}")
        events.emit(job_id, "system", "error", f"{task_name} failed: {exc}")


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

        t = threading.Thread(
            target=_run_pipeline,
            kwargs={
                "job_id":            job_id,
                "topic":             job["topic"],
                "tone":              job["tone"],
                "audience":          "general",
                "sections":          job["sections"],
                "generate_podcast":  job["generate_podcast"],
                "generate_video":    job["generate_video"],
                "generate_campaign": job["generate_campaign"],
                "generate_qa":       True,
                "worker_event":      new_event,
            }
        )
        t.daemon = True
        t.start()
        logger.info(f"🚀 Re-spawned background pipeline thread to resume job {job_id}")
