import asyncio
import threading
from pathlib import Path
from typing import Any

# Ensure backend directory resolution
_BACKEND_DIR = Path(__file__).resolve().parent.parent

# HITL approval events and revisions
_approval_events: dict[str, asyncio.Event] = {}
_plan_revisions: dict[str, Any] = {}
_direct_plan_updates: dict[str, Any] = {}
_worker_approval_events: dict[str, threading.Event] = {}

# Per-job lock to protect metadata.json writes from concurrent tasks
_job_file_locks: dict[str, threading.Lock] = {}

# Upload configurations
_UPLOADS_ROOT = _BACKEND_DIR / "uploads"
_SUPPORTED_UPLOAD_EXTS = {".pdf", ".docx", ".txt", ".md"}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
