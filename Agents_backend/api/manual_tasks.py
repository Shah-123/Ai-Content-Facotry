"""Focused handlers for on-demand post-generation tasks.

The background pipeline owns long-running graph execution. This module owns
the smaller, user-triggered tasks that operate on an existing job: media,
campaigns, academic evaluation, QA, and images.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

import event_bus as events
from api.schemas import GenerationConfig
from api.utils import _get_job_lock, _update_metadata_json, get_job_healed
from db import update_job

logger = logging.getLogger("api.manual_tasks")


@dataclass
class ManualTaskContext:
    job_id: str
    task_name: str
    job: dict[str, Any]
    base_path: Path
    meta_path: Path
    state: dict[str, Any]
    plan: Any
    job_lock: Any
    pipeline_loader: Callable[[], Any]


def run_manual_task(
    job_id: str,
    task_name: str,
    *,
    backend_dir: Path,
    pipeline_loader: Callable[[], Any],
) -> None:
    """Load one completed job and dispatch its requested follow-up task."""
    try:
        load_dotenv(backend_dir.parent / ".env")
        context = _load_context(job_id, task_name, pipeline_loader)
        events.emit(job_id, task_name, "started", f"Starting manual {task_name}...")
        _ensure_output_folders(context.base_path)

        handler = {
            "video": _handle_video,
            "podcast": _handle_podcast,
            "deepeval": _handle_deepeval,
            "campaign": _handle_campaign,
        }.get(task_name, _handle_content_task)
        handler(context)
    except Exception as exc:
        logger.exception("Manual %s failed: %s", task_name, exc)
        events.emit(job_id, "system", "error", f"{task_name} failed: {exc}")


def _load_context(job_id: str, task_name: str, pipeline_loader: Callable[[], Any]) -> ManualTaskContext:
    job = get_job_healed(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    config = GenerationConfig.model_validate(job.get("config", {}))
    base_path = Path(job["blog_folder"])
    meta_path = base_path / "metadata" / "metadata.json"
    meta = _read_json(meta_path) if meta_path.exists() else {}
    if not isinstance(meta, dict):
        meta = {}
    final_markdown = _read_blog_markdown(base_path, meta)
    plan = _read_plan(base_path)

    num_images = config.num_images
    generate_images = config.generate_images
    if task_name == "images":
        num_images = num_images if num_images > 0 else 2
        generate_images = True

    state = {
        "topic": job.get("topic", "Unknown"),
        "target_tone": config.tone,
        "target_keywords": config.keywords,
        "num_images": num_images,
        "generate_images": generate_images,
        "merged_md": final_markdown,
        "final": final_markdown,
        "blog_folder": str(base_path),
        "_job_id": job_id,
        "qa_verdict": meta.get("qa_verdict", "READY"),
        "qa_score": meta.get("qa_score", 0),
        "qa_issues": [],
        "revision_count": 0,
        "qa_fixed_claims": [],
        "plan": plan,
        "image_model": config.image_model,
        "image_size": config.image_size,
        "image_quality": config.image_quality,
        "image_style": config.image_style,
    }

    return ManualTaskContext(
        job_id=job_id,
        task_name=task_name,
        job=job,
        base_path=base_path,
        meta_path=meta_path,
        state=state,
        plan=plan,
        job_lock=_get_job_lock(job_id),
        pipeline_loader=pipeline_loader,
    )


def _handle_video(context: ManualTaskContext) -> None:
    from Graph.nodes import video_generator_node

    output_path = context.base_path / "video" / "short.mp4"
    if _is_nonempty_file(output_path):
        events.emit(context.job_id, context.task_name, "completed", "Video already exists. Skipping.")
        if not context.job.get("video_file"):
            update_job(context.job_id, video_file="video/short.mp4")
        return

    context.state.update(video_generator_node(context.state))
    source_path = context.state.get("video_path")
    if not _copy_generated_file(source_path, output_path):
        raise RuntimeError("Video file generation or saving failed (output file is missing or empty).")

    update_job(context.job_id, video_file="video/short.mp4")
    _update_metadata_json(context.meta_path, {"file_paths": {"video": str(output_path)}}, context.job_lock)
    events.emit(context.job_id, "system", "completed", "Video completed successfully.")


def _handle_podcast(context: ManualTaskContext) -> None:
    from Graph.nodes import podcast_node

    wav_path = context.base_path / "audio" / "podcast.wav"
    mp3_path = context.base_path / "audio" / "podcast.mp3"
    existing_path, existing_relative = _existing_podcast(wav_path, mp3_path)
    if existing_path:
        events.emit(context.job_id, context.task_name, "completed", "Podcast already exists. Skipping.")
        if not context.job.get("podcast_file"):
            update_job(context.job_id, podcast_file=existing_relative)
        return

    context.state.update(podcast_node(context.state))
    source_path = context.state.get("podcast_audio_path")
    destination = mp3_path if source_path and Path(source_path).suffix.lower() == ".mp3" else wav_path
    relative_path = "audio/podcast.mp3" if destination == mp3_path else "audio/podcast.wav"
    if not _copy_generated_file(source_path, destination):
        raise RuntimeError("Podcast file generation or saving failed (output file is missing or empty).")

    update_job(context.job_id, podcast_file=relative_path)
    _update_metadata_json(context.meta_path, {"file_paths": {"podcast": str(destination)}}, context.job_lock)
    events.emit(context.job_id, "system", "completed", "Podcast completed successfully.")


def _handle_deepeval(context: ManualTaskContext) -> None:
    from Graph.nodes import deepeval_evaluation_node

    evidence_path = context.base_path / "research" / "evidence.json"
    context.state["evidence"] = _read_json(evidence_path, warning_label="evidence.json", default=[]) if evidence_path.exists() else []

    result = deepeval_evaluation_node(context.state)
    scores = result.get("deepeval_scores")
    if not scores:
        events.emit(context.job_id, "system", "error", "Academic audit failed — no scores returned. Is deepeval installed?")
        return

    update_job(context.job_id, deepeval_scores=scores)
    _write_deepeval_report(context.base_path, scores)
    _update_metadata_json(context.meta_path, {"deepeval_scores": scores}, context.job_lock)
    events.emit(
        context.job_id,
        "system",
        "completed",
        "Academic audit (deepeval G-Eval) completed.",
        {"deepeval_scores": scores},
    )


def _handle_campaign(context: ManualTaskContext) -> None:
    from Graph.nodes import campaign_generator_node

    if context.job.get("social_linkedin") or context.job.get("social_twitter"):
        events.emit(context.job_id, context.task_name, "completed", "Social media already exists. Skipping.")
        return

    context.state.update(campaign_generator_node(context.state))
    slug = context.plan.blog_title.replace(" ", "_").lower()[:50] if context.plan else "blog"
    social_dir = context.base_path / "social_media"
    if context.state.get("linkedin_post"):
        (social_dir / f"linkedin_{slug}.txt").write_text(context.state["linkedin_post"], encoding="utf-8")
    if context.state.get("twitter_thread"):
        (social_dir / f"twitter_{slug}.md").write_text(context.state["twitter_thread"], encoding="utf-8")

    update_job(
        context.job_id,
        social_linkedin=context.state.get("linkedin_post", ""),
        social_twitter=context.state.get("twitter_thread", ""),
    )
    events.emit(context.job_id, "system", "completed", "Campaign completed successfully.")


def _handle_content_task(context: ManualTaskContext) -> None:
    if context.task_name == "images":
        from Graph.nodes import decide_images, generate_and_place_images

        context.state.update(decide_images(context.state))
        context.state.update(generate_and_place_images(context.state))
    elif context.task_name == "qa":
        from Graph.nodes import qa_agent_node, revision_node

        context.state.update(qa_agent_node(context.state))
        if context.state.get("qa_verdict") == "NEEDS_REVISION":
            context.state.update(revision_node(context.state))
            context.state.update(qa_agent_node(context.state))

    saved = _save_content(context)
    updates: dict[str, Any] = {}
    if context.task_name == "qa":
        updates.update(
            qa_score=context.state.get("qa_score"),
            qa_verdict=context.state.get("qa_verdict"),
            final_content=context.state.get("final"),
        )
    if saved.get("blog"):
        updates["blog_file"] = os.path.relpath(saved["blog"], context.base_path)
    if saved.get("blog_html"):
        updates["blog_html_file"] = os.path.relpath(saved["blog_html"], context.base_path)
    if context.task_name == "images" and "final" in context.state:
        updates["final_content"] = context.state["final"]
    if updates:
        update_job(context.job_id, **updates)

    events.emit(context.job_id, "system", "completed", f"{context.task_name.capitalize()} completed successfully.")


def _save_content(context: ManualTaskContext) -> dict[str, Any]:
    folders = {
        "base": str(context.base_path),
        "content": str(context.base_path / "content"),
        "social": str(context.base_path / "social_media"),
        "reports": str(context.base_path / "reports"),
        "assets": str(context.base_path / "assets" / "images"),
        "research": str(context.base_path / "research"),
        "audio": str(context.base_path / "audio"),
        "video": str(context.base_path / "video"),
        "metadata": str(context.base_path / "metadata"),
    }
    try:
        with context.job_lock:
            return context.pipeline_loader().save_blog_content(folders, context.state)
    except Exception as save_error:
        logger.warning("save_blog_content failed (%s), falling back to direct DB update", save_error)
        return {}


def _read_blog_markdown(base_path: Path, meta: dict[str, Any]) -> str:
    saved_path = meta.get("file_paths", {}).get("blog")
    if saved_path and Path(saved_path).exists():
        return Path(saved_path).read_text(encoding="utf-8")

    content_files = list((base_path / "content").glob("*.md"))
    candidates = content_files or list(base_path.glob("*.md"))
    if not candidates:
        raise FileNotFoundError(f"Could not locate blog markdown file in {base_path}")
    return candidates[0].read_text(encoding="utf-8")


def _read_plan(base_path: Path) -> Any:
    plan_path = base_path / "metadata" / "plan.json"
    if not plan_path.exists():
        return None
    from Graph.state import Plan
    plan_data = _read_json(plan_path)
    return Plan(**plan_data) if isinstance(plan_data, dict) else None


def _read_json(path: Path, warning_label: str | None = None, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception as error:
        if default is None:
            raise
        if warning_label:
            logger.warning("Could not load %s: %s", warning_label, error)
        return default


def _ensure_output_folders(base_path: Path) -> None:
    for directory in ("content", "social_media", "reports", "assets/images", "research", "audio", "video", "metadata"):
        (base_path / directory).mkdir(parents=True, exist_ok=True)


def _copy_generated_file(source: str | None, destination: Path) -> bool:
    if not source or not os.path.exists(source) or os.path.getsize(source) <= 0:
        return False
    try:
        if not os.path.samefile(source, destination):
            shutil.copy(source, destination)
    except (OSError, ValueError):
        shutil.copy(source, destination)
    return _is_nonempty_file(destination)


def _existing_podcast(wav_path: Path, mp3_path: Path) -> tuple[Path | None, str | None]:
    if _is_nonempty_file(mp3_path):
        return mp3_path, "audio/podcast.mp3"
    if _is_nonempty_file(wav_path):
        return wav_path, "audio/podcast.wav"
    return None, None


def _is_nonempty_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _write_deepeval_report(base_path: Path, scores: dict[str, Any]) -> None:
    try:
        report_path = base_path / "reports" / "deepeval_report.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "DEEPEVAL G-EVAL REPORT (Liu et al. 2023)",
            "=" * 60,
            "Library:        deepeval (official implementation)",
            "Score Scale:    0.0 (worst) - 1.0 (best)",
            f"Overall Score:  {scores.get('overall_score', 'N/A')}/1.0",
            "",
            "Rubric Evaluations:",
            "-" * 60,
        ]
        labels = {
            "coherence": "1. COHERENCE",
            "relevance": "2. RELEVANCE",
            "accuracy": "3. ACCURACY & GROUNDING",
            "tone_alignment": "4. TONE ALIGNMENT",
        }
        for key, label in labels.items():
            criterion = scores.get(key) or {}
            lines.extend([f"{label}: {criterion.get('score', 'N/A')}/1.0", f"   Reasoning: {criterion.get('reasoning', 'N/A')}", ""])
        report_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as report_error:
        logger.warning("Could not write deepeval_report.txt: %s", report_error)
