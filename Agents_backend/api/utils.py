import os
import json
import logging
from pathlib import Path
from typing import Optional, Any
import threading

from db import get_job, list_jobs, update_job
from api.state import _job_file_locks

logger = logging.getLogger("api.utils")

def _safe_upload_name(name: str) -> str:
    """Strip path components and disallow risky characters in filenames."""
    base = os.path.basename(name or "")
    # Replace anything outside [A-Za-z0-9._-] with underscore
    cleaned = "".join(c if c.isalnum() or c in "._- " else "_" for c in base).strip()
    return cleaned or "upload"


def _get_job_lock(job_id: str) -> threading.Lock:
    """Get or create a threading lock for a specific job's file operations."""
    if job_id not in _job_file_locks:
        _job_file_locks[job_id] = threading.Lock()
    return _job_file_locks[job_id]


def _update_metadata_json(meta_path: Path, updates: dict, job_lock: threading.Lock):
    """Thread-safe read-modify-write of metadata.json.

    Only merges the provided keys into the existing metadata, so
    concurrent tasks (video, podcast, campaign) never clobber each
    other's entries.
    """
    with job_lock:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # Merge top-level keys
        for k, v in updates.items():
            if k == "file_paths" and isinstance(v, dict):
                # Deep-merge file_paths so each task only adds its own entry
                meta.setdefault("file_paths", {}).update(v)
            else:
                meta[k] = v
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)


def _verify_and_clean_job_files(job: dict) -> dict:
    """Check if registered files for a job exist on disk and are valid.
    If not, surgically clear their paths in the DB and metadata.json.
    """
    job_id = job["id"]
    base_path = job.get("blog_folder")
    if not base_path or not os.path.exists(base_path):
        # Blog folder itself is missing or not set; clear all file paths in DB
        fields_to_clear = {}
        for field in ("blog_file", "blog_html_file", "podcast_file", "video_file"):
            if job.get(field):
                fields_to_clear[field] = None
                job[field] = None
        if fields_to_clear:
            update_job(job_id, **fields_to_clear)
        return job

    updates = {}
    meta_updated = False
    meta_path = Path(base_path) / "metadata" / "metadata.json"

    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    file_paths = meta.get("file_paths", {})

    for field, key, check_size in [
        ("blog_file", "blog", False),
        ("blog_html_file", "blog_html", False),
        ("podcast_file", "podcast", True),
        ("video_file", "video", True),
    ]:
        val = job.get(field)
        if val:
            full_path = Path(base_path) / val
            is_valid = full_path.exists()
            if is_valid and check_size:
                is_valid = full_path.stat().st_size > 0

            if not is_valid:
                updates[field] = None
                job[field] = None
                if key in file_paths:
                    file_paths[key] = None
                    meta_updated = True

    if updates:
        update_job(job_id, **updates)
        if meta_updated and meta_path.exists():
            job_lock = _get_job_lock(job_id)
            try:
                _update_metadata_json(meta_path, {"file_paths": file_paths}, job_lock)
            except Exception as e:
                logger.warning(f"Failed to update metadata.json during healing for job {job_id}: {e}")

    return job


def get_job_healed(job_id: str) -> Optional[dict]:
    """Retrieve job by ID and run self-healing verification on its files."""
    job = get_job(job_id)
    if job:
        job = _verify_and_clean_job_files(job)
    return job


def list_jobs_healed(limit: int = 50) -> list[dict]:
    """Retrieve jobs list and run self-healing verification on their files."""
    jobs = list_jobs(limit)
    return [_verify_and_clean_job_files(j) for j in jobs]
