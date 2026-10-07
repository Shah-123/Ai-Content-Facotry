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


def test_the_job_list_is_a_summary_without_the_heavy_fields(tmp_path: Path, monkeypatch):
    """The sidebar polls this every 15 s; it must not ship whole articles."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "web_jobs.db")
    db.init_db()
    job = db.create_job("List me", config={"tone": "technical", "sections": 4})
    db.update_job(job["id"], status="completed", final_content="x" * 10_000,
                  plan_json='{"blog_title": "T"}', social_linkedin="post",
                  geval_scores='{"overall_score": 8}')

    [listed] = db.list_jobs()

    assert (listed["id"], listed["topic"], listed["status"]) == (job["id"], "List me", "completed")
    assert listed["config"]["tone"] == "technical"   # still rebuilt from config_json
    for heavy in ("final_content", "plan_json", "social_linkedin", "social_twitter"):
        assert heavy not in listed
    assert listed["plan"] is None and listed["geval_scores"] is None
    assert db.get_job(job["id"])["final_content"] == "x" * 10_000  # the full row is unchanged
