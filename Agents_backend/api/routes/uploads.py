import os
import uuid
import logging
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File

from api.state import _UPLOADS_ROOT, _SUPPORTED_UPLOAD_EXTS, _MAX_UPLOAD_BYTES
from api.utils import _safe_upload_name

logger = logging.getLogger("api.routes.uploads")
router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("")
async def upload_document(file: UploadFile = File(...)):
    """Accept a single document, parse it, extract evidence, and persist
    everything under uploads/<upload_id>/. Returns metadata the frontend
    needs to wire the upload to a subsequent /api/jobs request.
    """
    filename = _safe_upload_name(file.filename or "upload")
    ext = Path(filename).suffix.lower()
    if ext not in _SUPPORTED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_format",
                "reason": f"File type '{ext or '?'}' is not supported.",
                "supported": sorted(_SUPPORTED_UPLOAD_EXTS),
            },
        )

    # Stream the upload into the chosen folder while enforcing the size cap.
    upload_id = uuid.uuid4().hex
    upload_dir = _UPLOADS_ROOT / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename

    bytes_written = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB at a time
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_UPLOAD_BYTES:
                    out.close()
                    target.unlink(missing_ok=True)
                    upload_dir.rmdir()
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "error": "file_too_large",
                            "reason": f"Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                        },
                    )
                out.write(chunk)
    finally:
        await file.close()

    # Heavy work: parse → chunk → LLM-extract evidence. Off the event loop.
    try:
        from Graph.agents.document_ingest import ingest_upload
        meta = await asyncio.to_thread(ingest_upload, upload_dir, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Upload ingest failed for {upload_id}: {exc}")
        # Clean up partial state so a retry doesn't accumulate junk.
        try:
            for child in upload_dir.iterdir():
                child.unlink(missing_ok=True)
            upload_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(
            status_code=422,
            detail={"error": "ingest_failed", "reason": str(exc)},
        )

    return {
        "upload_id": upload_id,
        "filename": meta.get("filename", filename),
        "format": meta.get("format"),
        "bytes": bytes_written,
        "pages": meta.get("pages", 0),
        "chunks": meta.get("chunks", 0),
        "chunks_processed": meta.get("chunks_processed", 0),
        "evidence_count": meta.get("evidence_count", 0),
        "truncated": meta.get("truncated", False),
        "derived_topic": meta.get("derived_topic", ""),
        "preview": meta.get("preview", ""),
    }


@router.get("/{upload_id}")
async def get_upload(upload_id: str):
    """Return previously computed metadata for an upload, or 404."""
    # Defend against path traversal — only accept simple uuid-like strings.
    if not upload_id or any(c in upload_id for c in "/\\.:"):
        raise HTTPException(status_code=400, detail="Invalid upload_id.")
    upload_dir = _UPLOADS_ROOT / upload_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Upload not found.")
    from Graph.agents.document_ingest import load_upload_metadata
    meta = load_upload_metadata(upload_dir)
    if not meta:
        raise HTTPException(status_code=404, detail="Upload metadata missing.")
    return {"upload_id": upload_id, **meta}
