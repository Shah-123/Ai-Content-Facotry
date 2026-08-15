"""Auth gate + job-file path containment."""

from pathlib import Path

from api import auth


def test_auth_is_disabled_when_no_key_is_configured(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert auth.api_key_is_valid(None) is True
    assert auth.api_key_is_valid("anything") is True


def test_auth_requires_an_exact_match_when_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret-value")
    assert auth.api_key_is_valid("s3cret-value") is True
    assert auth.api_key_is_valid("s3cret-valu") is False
    assert auth.api_key_is_valid("") is False
    assert auth.api_key_is_valid(None) is False


def test_blank_api_key_env_leaves_auth_disabled(monkeypatch):
    """A key of only whitespace must not silently lock everyone out."""
    monkeypatch.setenv("API_KEY", "   ")
    assert auth.api_key_is_valid(None) is True


def test_sibling_job_folder_is_not_reachable_by_path_traversal(tmp_path: Path):
    """Regression: `str.startswith` let job `topic_123` read `topic_1234/`.

    Mirrors the containment check in api/routes/jobs.py::serve_file.
    """
    base = (tmp_path / "blogs" / "topic_123").resolve()
    base.mkdir(parents=True)
    sibling = (tmp_path / "blogs" / "topic_1234").resolve()
    sibling.mkdir(parents=True)
    (sibling / "secret.txt").write_text("other job's data", encoding="utf-8")

    escaped = (base / "../topic_1234/secret.txt").resolve()

    # The old check passed this — the shared `topic_123` prefix fooled it.
    assert str(escaped).startswith(str(base)) is True
    # The containment check rejects it.
    assert escaped.is_relative_to(base) is False

    # A legitimate in-folder path still resolves fine.
    assert (base / "content/post.md").resolve().is_relative_to(base) is True
