"""Backward-compatible exports facade.

The application's one export implementation now lives in :mod:`exporters`.
This module remains only to avoid breaking older scripts that import
``Graph.export_manager`` directly.
"""

import logging
from pathlib import Path
from typing import List, Optional

from exporters import export_all, export_to_docx, export_to_html, export_to_pdf

logger = logging.getLogger("blog_pipeline")


def export_html(markdown_text: str, output_path: str, title: str = "Blog Post") -> Optional[str]:
    """Compatibility wrapper for the shared HTML exporter."""
    path = _with_extension(output_path, ".html")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export_to_html(title, markdown_text, _job_dir(path)), encoding="utf-8")
        return str(path)
    except Exception:
        logger.exception("Failed to export HTML")
        return None


def export_pdf(markdown_text: str, output_path: str, title: str = "Blog Post") -> Optional[str]:
    """Compatibility wrapper for the shared PDF exporter."""
    path = _with_extension(output_path, ".pdf")
    try:
        export_to_pdf(title, markdown_text, path, _job_dir(path))
        return str(path)
    except Exception:
        logger.exception("Failed to export PDF")
        return None


def export_docx(markdown_text: str, output_path: str, title: str = "Blog Post") -> Optional[str]:
    """Compatibility wrapper for the shared DOCX exporter."""
    path = _with_extension(output_path, ".docx")
    try:
        export_to_docx(title, markdown_text, path, _job_dir(path))
        return str(path)
    except Exception:
        logger.exception("Failed to export DOCX")
        return None


def _with_extension(output_path: str, extension: str) -> Path:
    path = Path(output_path)
    return path if path.suffix.lower() == extension else path.with_suffix(extension)


def _job_dir(output_path: Path) -> Path:
    """Derive a job directory from the conventional ``content`` folder."""
    return output_path.parent.parent if output_path.parent.name == "content" else output_path.parent


__all__: List[str] = [
    "export_all",
    "export_html",
    "export_pdf",
    "export_docx",
]
