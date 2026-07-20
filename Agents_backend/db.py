"""
db.py — SQLite persistence layer for the web API.
Manages the `web_jobs` table that tracks all blog generation jobs
submitted through the web interface.
"""
import  os 
import sqlite3
import json
import uuid
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

# Database lives in a data/ subdirectory to avoid uvicorn reload loops
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = _DATA_DIR / "web_jobs.db"


# ============================================================================
# SCHEMA
# ============================================================================

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS web_jobs (
    id                   TEXT PRIMARY KEY,
    topic                TEXT NOT NULL,
    tone                 TEXT DEFAULT 'professional',
    sections             INTEGER DEFAULT 3,
    status               TEXT DEFAULT 'pending',
    created_at           TEXT,
    completed_at         TEXT,
    blog_folder          TEXT,
    qa_score             REAL,
    qa_verdict           TEXT,
    blog_evaluator_score REAL,
    blog_file            TEXT,
    blog_html_file       TEXT,
    podcast_file         TEXT,
    video_file           TEXT,
    plan_json            TEXT,
    error_message        TEXT,
    word_count           INTEGER,
    final_content        TEXT,
    social_linkedin      TEXT,
    social_twitter       TEXT,
    generate_podcast     INTEGER DEFAULT 0,
    generate_video       INTEGER DEFAULT 0,
    generate_campaign    INTEGER DEFAULT 0,
    geval_scores         TEXT,
    deepeval_scores      TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist and run column migrations if needed."""
    with _get_conn() as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()

        # Schema auto-migration: check if geval_scores column exists
        cursor = conn.execute("PRAGMA table_info(web_jobs)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "geval_scores" not in columns:
            print("[DB Migration] Migrating database: adding geval_scores column to web_jobs...")
            try:
                conn.execute("ALTER TABLE web_jobs ADD COLUMN geval_scores TEXT")
                conn.commit()
                print("   [Success] geval_scores column successfully added.")
            except Exception as e:
                print(f"   [Error] Migration failed: {e}")

        if "deepeval_scores" not in columns:
            print("[DB Migration] Migrating database: adding deepeval_scores column to web_jobs...")
            try:
                conn.execute("ALTER TABLE web_jobs ADD COLUMN deepeval_scores TEXT")
                conn.commit()
                print("   [Success] deepeval_scores column successfully added.")
            except Exception as e:
                print(f"   [Error] Migration failed: {e}")


# ============================================================================
# CRUD
# ============================================================================

def create_job(topic: str, tone: str = "professional", sections: int = 3,
               generate_podcast: bool = False, generate_video: bool = False,
               generate_campaign: bool = False) -> dict:
    """Insert a new job row and return the job dict."""
    job_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO web_jobs
               (id, topic, tone, sections, status, created_at,
                generate_podcast, generate_video, generate_campaign)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (job_id, topic, tone, sections, "pending", created_at,
             int(generate_podcast), int(generate_video), int(generate_campaign))
        )
        conn.commit()
    return get_job(job_id)


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a single job by id."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM web_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict]:
    """List jobs sorted newest-first."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM web_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_job(job_id: str, **fields) -> Optional[dict]:
    """Update arbitrary fields on a job."""
    if not fields:
        return get_job(job_id)
    
    # Ensure blog_folder is relative to the backend directory before saving
    if "blog_folder" in fields and fields["blog_folder"]:
        backend_dir = Path(__file__).parent.resolve()
        path = Path(fields["blog_folder"])
        if path.is_absolute():
            try:
                if path.resolve().is_relative_to(backend_dir):
                    fields["blog_folder"] = os.path.relpath(path, backend_dir).replace("\\", "/")
            except Exception:
                try:
                    if str(path.resolve()).startswith(str(backend_dir)):
                        fields["blog_folder"] = os.path.relpath(path, backend_dir).replace("\\", "/")
                except Exception:
                    pass

    # Serialize dict / list fields automatically
    for k, v in list(fields.items()):
        if k in ("geval_scores", "deepeval_scores") and v is not None and not isinstance(v, str):
            fields[k] = json.dumps(v)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _get_conn() as conn:
        conn.execute(
            f"UPDATE web_jobs SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    """Delete a job row by id. Returns True if row was deleted."""
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM web_jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0


def set_job_running(job_id: str, blog_folder: str):
    update_job(job_id, status="running", blog_folder=blog_folder)


def set_job_awaiting_approval(job_id: str, plan_json: str):
    update_job(job_id, status="awaiting_approval", plan_json=plan_json)


def set_job_completed(job_id: str, **result_fields):
    update_job(
        job_id,
        status="completed",
        completed_at=datetime.now(UTC).isoformat(),
        **result_fields,
    )


def set_job_failed(job_id: str, error: str):
    update_job(
        job_id,
        status="failed",
        completed_at=datetime.now(UTC).isoformat(),
        error_message=str(error)[:2000],
    )


# ============================================================================
# HELPER
# ============================================================================

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    
    # Ensure blog_folder is returned as absolute path
    if d.get("blog_folder"):
        path = Path(d["blog_folder"])
        if not path.is_absolute():
            backend_dir = Path(__file__).parent.resolve()
            d["blog_folder"] = str((backend_dir / path).resolve()).replace("\\", "/")

    # Parse plan JSON if present
    if d.get("plan_json"):
        try:
            d["plan"] = json.loads(d["plan_json"])
        except Exception:
            d["plan"] = None
    else:
        d["plan"] = None

    # Parse geval_scores JSON if present
    if d.get("geval_scores"):
        try:
            d["geval_scores"] = json.loads(d["geval_scores"])
        except Exception:
            d["geval_scores"] = None
    else:
        d["geval_scores"] = None

    # Parse deepeval_scores JSON if present
    if d.get("deepeval_scores"):
        try:
            d["deepeval_scores"] = json.loads(d["deepeval_scores"])
        except Exception:
            d["deepeval_scores"] = None
    else:
        d["deepeval_scores"] = None

    # Expose boolean-style flags as booleans
    for flag in ("generate_podcast", "generate_video", "generate_campaign"):
        if flag in d:
            d[flag] = bool(d[flag])
    return d


# Auto-init on import
init_db()
