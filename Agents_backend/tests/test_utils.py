"""
Tests for Graph/agents/utils.py — shared utility helpers.
"""
import pytest
from Graph.agents.utils import _safe_slug


class TestSafeSlug:
    """Tests for _safe_slug()."""

    def test_basic_conversion(self):
        assert _safe_slug("Hello World") == "hello_world"

    def test_strips_special_characters(self):
        assert _safe_slug("AI & Healthcare: The Future!") == "ai_healthcare_the_future"

    def test_handles_multiple_spaces(self):
        slug = _safe_slug("too   many    spaces")
        assert "  " not in slug  # no double underscores from collapsed spaces
        assert slug == "too_many_spaces"

    def test_returns_fallback_for_empty_string(self):
        assert _safe_slug("") == "blog"

    def test_returns_fallback_for_only_special_chars(self):
        assert _safe_slug("!@#$%^&*()") == "blog"

    def test_preserves_hyphens_and_underscores(self):
        slug = _safe_slug("my-topic_name")
        assert "my-topic_name" == slug


# ---------------------------------------------------------------------------
# Every model client must be bounded in time
# ---------------------------------------------------------------------------


class TestRequestTimeoutsAreConfigured:
    """Unset, langchain-openai inherits the OpenAI SDK's 600s read timeout and
    retries twice: one wedged request occupies a worker thread for ~30 minutes,
    indistinguishable in the logs from a slow model. Pipeline runs live in
    FastAPI's bounded thread pool, and jobs awaiting approval already hold
    threads for up to 20 minutes, so an unbounded call compounds into API-wide
    starvation.
    """

    def test_all_shared_clients_have_a_timeout(self):
        from Graph.agents import utils

        for name in ("llm_fast", "llm_quality", "llm_judge", "llm_planner"):
            client = getattr(utils, name)
            timeout = getattr(client, "request_timeout", None) or getattr(client, "timeout", None)
            assert timeout, f"{name} has no request timeout — worst case is unbounded"
            assert timeout == utils._REQUEST_TIMEOUT

    def test_get_llm_applies_the_timeout(self):
        from Graph.agents.utils import get_llm, _REQUEST_TIMEOUT

        client = get_llm()
        timeout = getattr(client, "request_timeout", None) or getattr(client, "timeout", None)
        assert timeout == _REQUEST_TIMEOUT

    def test_embeddings_client_is_bounded(self):
        """Semantic chunking embeds every sentence in one call — the largest request made."""
        from Graph.agents.document_ingest import get_embeddings_model
        from Graph.agents.utils import _REQUEST_TIMEOUT

        model = get_embeddings_model()
        timeout = getattr(model, "request_timeout", None) or getattr(model, "timeout", None)
        assert timeout == _REQUEST_TIMEOUT

    def test_timeout_is_overridable_by_environment(self, monkeypatch):
        """A slower model must be accommodatable without a code change."""
        import importlib
        from Graph.agents import utils

        monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "45")
        reloaded = importlib.reload(utils)
        try:
            assert reloaded._REQUEST_TIMEOUT == 45.0
        finally:
            monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
            importlib.reload(utils)  # restore the shared module for other tests

    def test_no_module_builds_a_bare_unbounded_client(self):
        """Bare ChatOpenAI(...) bypasses the timeout; route through get_llm()."""
        import pathlib
        import re

        backend = pathlib.Path(__file__).resolve().parent.parent
        offenders = []
        for path in backend.rglob("*.py"):
            if "tests" in path.parts or path.name == "utils.py":
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\bChatOpenAI\s*\(", line):
                    offenders.append(f"{path.relative_to(backend)}:{i}")

        assert not offenders, (
            "these construct ChatOpenAI directly and so inherit the SDK's "
            "600s default; use get_llm() instead:\n  " + "\n  ".join(offenders)
        )
