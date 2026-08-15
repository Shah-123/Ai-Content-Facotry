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
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

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
    deepeval_scores      TEXT,
    image_model          TEXT DEFAULT 'dall-e-3',
    image_size           TEXT DEFAULT '1024x1024',
    image_quality        TEXT DEFAULT 'standard',
    image_style          TEXT DEFAULT 'vivid',
    config_json          TEXT DEFAULT '{}'
);
"""


DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")))


def _format_sql(sql: str) -> str:
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


import threading

_db_lock = threading.Lock()


@contextmanager
def get_db():
    """Context manager for Database connections (PostgreSQL or SQLite) that guarantees closure and thread safety."""
    if USE_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
            try:
                yield conn
            finally:
                conn.close()
        except ImportError:
            import psycopg2
            from psycopg2.extras import DictCursor
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
            try:
                yield conn
            finally:
                conn.close()
    else:
        conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def init_db():
    """Create tables if they don't exist and run column migrations if needed (thread-safe)."""
    with _db_lock:
        with get_db() as conn:
            conn.execute(_format_sql(_CREATE_TABLE))
            conn.commit()

            if not USE_POSTGRES:
                # Schema auto-migration for SQLite
                cursor = conn.execute(_format_sql("PRAGMA table_info(web_jobs)"))
                columns = [row["name"] for row in cursor.fetchall()]
                if "geval_scores" not in columns:
                    try:
                        conn.execute(_format_sql("ALTER TABLE web_jobs ADD COLUMN geval_scores TEXT"))
                        conn.commit()
                    except Exception as e:
                        print(f"   [Error] Migration failed: {e}")

                if "deepeval_scores" not in columns:
                    try:
                        conn.execute(_format_sql("ALTER TABLE web_jobs ADD COLUMN deepeval_scores TEXT"))
                        conn.commit()
                    except Exception as e:
                        print(f"   [Error] Migration failed: {e}")

                for col in ("image_model", "image_size", "image_quality", "image_style", "config_json"):
                    if col not in columns:
                        try:
                            conn.execute(_format_sql(f"ALTER TABLE web_jobs ADD COLUMN {col} TEXT"))
                            conn.commit()
                        except Exception as e:
                            print(f"   [Error] Migration of {col} failed: {e}")
            else:
                conn.execute("ALTER TABLE web_jobs ADD COLUMN IF NOT EXISTS config_json TEXT DEFAULT '{}'")
                conn.commit()


# ============================================================================
# CRUD
# ============================================================================

def create_job(topic: str, tone: str = "professional", sections: int = 3,
               generate_podcast: bool = False, generate_video: bool = False,
               generate_campaign: bool = False,
               image_model: str = "dall-e-3", image_size: str = "1024x1024",
               image_quality: str = "standard", image_style: str = "vivid",
               config: Optional[dict[str, Any]] = None) -> dict:
    """Insert a new job row and return the job dict."""
    job_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()
    job_config = _build_job_config(
        config=config,
        tone=tone,
        sections=sections,
        generate_podcast=generate_podcast,
        generate_video=generate_video,
        generate_campaign=generate_campaign,
        image_model=image_model,
        image_size=image_size,
        image_quality=image_quality,
        image_style=image_style,
    )
    with get_db() as conn:
        conn.execute(
            _format_sql("""INSERT INTO web_jobs
               (id, topic, tone, sections, status, created_at,
                generate_podcast, generate_video, generate_campaign,
                image_model, image_size, image_quality, image_style, config_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""),
            (job_id, topic, job_config["tone"], job_config["sections"], "pending", created_at,
             int(job_config["generate_podcast"]), int(job_config["generate_video"]), int(job_config["generate_campaign"]),
             job_config["image_model"], job_config["image_size"], job_config["image_quality"], job_config["image_style"],
             json.dumps(job_config))
        )
        conn.commit()
    return get_job(job_id)


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a single job by id."""
    with get_db() as conn:
        cursor = conn.execute(
            _format_sql("SELECT * FROM web_jobs WHERE id = ?"), (job_id,)
        )
        row = cursor.fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict]:
    """List jobs sorted newest-first."""
    with get_db() as conn:
        cursor = conn.execute(
            _format_sql("SELECT * FROM web_jobs ORDER BY created_at DESC LIMIT ?"), (limit,)
        )
        rows = cursor.fetchall()
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
        if k in ("geval_scores", "deepeval_scores", "config_json") and v is not None and not isinstance(v, str):
            fields[k] = json.dumps(v)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_db() as conn:
        conn.execute(
            _format_sql(f"UPDATE web_jobs SET {set_clause} WHERE id = ?"), values
        )
        conn.commit()
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    """Delete a job row by id. Returns True if row was deleted."""
    with get_db() as conn:
        cursor = conn.execute(_format_sql("DELETE FROM web_jobs WHERE id = ?"), (job_id,))
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

    # `config_json` is the durable source of truth for all generation inputs.
    # Legacy rows are transparently populated from their original columns.
    d["config"] = _build_job_config(config=_read_json(d.get("config_json")), **d)
    
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


def _read_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _build_job_config(config: Optional[dict[str, Any]] = None, **legacy: Any) -> dict[str, Any]:
    """Merge persisted configuration with safe defaults and legacy job columns."""
    defaults = {
        "tone": legacy.get("tone") or "professional",
        "audience": legacy.get("audience") or "general",
        "sections": legacy.get("sections") or 3,
        "keywords": legacy.get("keywords") or [],
        "generate_podcast": bool(legacy.get("generate_podcast", False)),
        "generate_video": bool(legacy.get("generate_video", False)),
        "generate_campaign": bool(legacy.get("generate_campaign", False)),
        "generate_qa": bool(legacy.get("generate_qa", True)),
        "generate_images": bool(legacy.get("generate_images", False)),
        "num_images": legacy.get("num_images") or 0,
        "upload_id": legacy.get("upload_id"),
        "source_mode": legacy.get("source_mode") or "hybrid",
        "selected_model": legacy.get("selected_model") or "gpt-5-mini",
        "image_model": legacy.get("image_model") or "dall-e-3",
        "image_size": legacy.get("image_size") or "1024x1024",
        "image_quality": legacy.get("image_quality") or "standard",
        "image_style": legacy.get("image_style") or "vivid",
        "export_formats": legacy.get("export_formats") or ["html"],
    }
    defaults.update(config or {})
    return defaults


# Auto-init on import
init_db()
