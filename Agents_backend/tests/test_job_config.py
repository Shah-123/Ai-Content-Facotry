"""Regression tests for durable generation-job configuration."""

from pathlib import Path

import db


def test_create_job_preserves_the_complete_generation_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "web_jobs.db")
    db.init_db()

    config = {
        "tone": "technical",
        "audience": "software engineers",
        "sections": 5,
        "keywords": ["retrieval augmented generation", "LLM"],
        "generate_podcast": True,
        "generate_video": True,
        "generate_campaign": True,
        "generate_qa": False,
        "generate_images": True,
        "num_images": 4,
        "upload_id": "upload-123",
        "source_mode": "closed_book",
        "selected_model": "gpt-5-mini",
        "image_model": "dall-e-3",
        "image_size": "1792x1024",
        "image_quality": "hd",
        "image_style": "natural",
        "export_formats": ["html", "pdf"],
    }

    job = db.create_job("Configuration persistence", config=config)

    assert job["config"] == config
    assert job["tone"] == "technical"
    assert job["sections"] == 5
    assert job["generate_video"] is True
