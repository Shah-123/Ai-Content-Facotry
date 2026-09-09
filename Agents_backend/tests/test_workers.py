"""
Tests for Graph/agents/workers.py — section creation and unpacking helpers.

_make_section(), _unpack_section(), and _get_assigned_evidence() are pure
contract-enforcing functions with no LLM dependencies.
"""
import pytest
from Graph.state import Task, EvidenceItem
from Graph.agents.workers import _make_section, _unpack_section, _get_assigned_evidence


# ========================================================================
# _make_section
# ========================================================================

class TestMakeSection:
    """Tests for _make_section()."""

    def test_returns_correct_tuple(self):
        result = _make_section(0, "Hello World")
        assert result == (0, "Hello World")
        assert isinstance(result, tuple)

    def test_rejects_non_int_task_id(self):
        with pytest.raises(AssertionError, match="task_id must be int"):
            _make_section("0", "content")

    def test_rejects_non_str_content(self):
        with pytest.raises(AssertionError, match="content must be str"):
            _make_section(0, 12345)


# ========================================================================
# _unpack_section
# ========================================================================

class TestUnpackSection:
    """Tests for _unpack_section()."""

    def test_unpacks_valid_tuple(self):
        task_id, content = _unpack_section((3, "Section content"))
        assert task_id == 3
        assert content == "Section content"

    def test_unpacks_valid_list(self):
        task_id, content = _unpack_section([1, "Content from list"])
        assert task_id == 1
        assert content == "Content from list"

    def test_rejects_wrong_length(self):
        with pytest.raises(ValueError, match="Malformed section entry"):
            _unpack_section((1, "a", "b"))

    def test_rejects_non_sequence(self):
        with pytest.raises(ValueError, match="Malformed section entry"):
            _unpack_section("not a tuple")

    def test_rejects_non_int_task_id(self):
        with pytest.raises(ValueError, match="task_id must be int"):
            _unpack_section(("zero", "content"))

    def test_rejects_non_str_content(self):
        with pytest.raises(ValueError, match="content must be str"):
            _unpack_section((0, 999))


# ========================================================================
# _get_assigned_evidence
# ========================================================================

def _make_evidence(n: int) -> list:
    """Helper to create N dummy evidence items."""
    return [
        EvidenceItem(
            title=f"Source {i}", url=f"https://example.com/{i}",
            snippet=f"Snippet {i}", published_at=None, source=f"s{i}.com",
        )
        for i in range(n)
    ]


class TestGetAssignedEvidence:
    """Tests for _get_assigned_evidence()."""

    def test_returns_assigned_slice(self):
        task = Task(id=0, title="T", goal="G", bullets=["B"],
                    assigned_evidence_indices=[1, 3])
        evidence = _make_evidence(5)
        result = _get_assigned_evidence(task, evidence)
        assert len(result) == 2
        assert result[0].title == "Source 1"
        assert result[1].title == "Source 3"

    def test_fallback_when_no_indices(self):
        task = Task(id=0, title="T", goal="G", bullets=["B"],
                    assigned_evidence_indices=[])
        evidence = _make_evidence(3)
        result = _get_assigned_evidence(task, evidence)
        assert result == evidence  # full list returned

    def test_fallback_when_evidence_empty(self):
        task = Task(id=0, title="T", goal="G", bullets=["B"],
                    assigned_evidence_indices=[0, 1])
        result = _get_assigned_evidence(task, [])
        assert result == []

    def test_skips_out_of_bounds_indices(self):
        task = Task(id=0, title="T", goal="G", bullets=["B"],
                    assigned_evidence_indices=[0, 99])
        evidence = _make_evidence(3)
        result = _get_assigned_evidence(task, evidence)
        assert len(result) == 1
        assert result[0].title == "Source 0"


# ---------------------------------------------------------------------------
# `final` must be the article and only the article
# ---------------------------------------------------------------------------


class TestFinalContainsNoPublisherMetadata:
    """The QA auditor, in-house G-Eval, DeepEval and the keyword optimizer all
    score `state["final"]`. When merge_content appended a rendered SEO block
    (meta-title, meta-description, keyword list) to the article, every one of
    those scores was partly grading a metadata footer instead of prose — and
    readers received the post's own meta description printed under the article.

    The metadata now lives in `state["seo_metadata"]` and is written to
    reports/seo_metadata.txt by save_blog_content().
    """

    def test_seo_generator_returns_a_dict_not_a_markdown_block(self):
        import inspect
        from Graph.agents import workers

        sig = inspect.signature(workers._generate_seo_metadata)
        assert sig.return_annotation is not tuple, (
            "_generate_seo_metadata must return metadata only, never a "
            "(dict, markdown) pair — the markdown half is what leaked into final"
        )

    def test_merge_content_does_not_append_an_seo_block(self):
        import inspect
        from Graph.agents import workers

        src = inspect.getsource(workers.merge_content)
        code = "\n".join(
            l for l in src.splitlines() if not l.lstrip().startswith("#")
        )
        assert "{seo_block}" not in code, "SEO block is being appended to the article again"
        assert "seo_block" not in code, "seo_block must not exist in merge_content"

    def test_reading_time_survives_extraction_failure(self):
        """Reading time is computed locally, so a failed LLM call must not lose it."""
        from Graph.agents.workers import _generate_seo_metadata
        from unittest.mock import patch
        from Graph.state import Plan, Task

        plan = Plan(
            blog_title="T", tone="professional", audience="general",
            tasks=[Task(id=0, title="S", goal="g", bullets=["b"])],
        )
        body = " ".join(["word"] * 476)  # 476 / 238 = exactly 2 minutes

        with patch("Graph.agents.workers.llm") as fake:
            fake.with_structured_output.side_effect = RuntimeError("no api")
            fake.invoke.side_effect = RuntimeError("no api")
            out = _generate_seo_metadata(body, plan, {})

        assert isinstance(out, dict)
        assert out["reading_time_minutes"] == 2
