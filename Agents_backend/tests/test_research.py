"""
Tests for the research node's zero-evidence gate.

Regression target: the `closed_book_evergreen` golden run shipped 2,825 words
with router_mode="hybrid", evidence_count=0 and a READY verdict — a completely
ungrounded post that every downstream consumer (orchestrator prompt,
metadata.json, run README, golden harness) still reported as source-grounded.

`_research_result` is the single place both of research_node's return paths
converge, so the gate is tested there plus once end-to-end through the node.
"""

from unittest.mock import patch

from Graph.agents import research as research_mod
from Graph.agents.research import _research_result, research_node
from Graph.state import EvidenceItem


def _evidence(url: str = "https://example.com/a") -> EvidenceItem:
    return EvidenceItem(
        title="A source",
        url=url,
        snippet="A verifiable fact about the topic.",
        published_at=None,
        source="example.com",
    )


# ---------------------------------------------------------------------------
# _research_result — the gate itself
# ---------------------------------------------------------------------------


def test_downgrades_hybrid_to_closed_book_when_no_evidence():
    out = _research_result({"mode": "hybrid", "_job_id": ""}, [])
    assert out["evidence"] == []
    assert out["mode"] == "closed_book"
    assert out["needs_research"] is False


def test_downgrades_open_book_to_closed_book_when_no_evidence():
    out = _research_result({"mode": "open_book", "_job_id": ""}, [])
    assert out["mode"] == "closed_book"
    assert out["needs_research"] is False


def test_keeps_mode_when_evidence_was_found():
    out = _research_result({"mode": "hybrid", "_job_id": ""}, [_evidence()])
    assert "mode" not in out, "mode must not be touched when evidence exists"
    assert "needs_research" not in out
    assert len(out["evidence"]) == 1


def test_already_closed_book_is_left_alone():
    """No downgrade to apply — and no misleading 'downgraded' event."""
    out = _research_result({"mode": "closed_book", "_job_id": ""}, [])
    assert out == {"evidence": []}


def test_missing_mode_is_treated_as_closed_book():
    """A state with no mode key must not raise, and must not be downgraded."""
    out = _research_result({"_job_id": ""}, [])
    assert out == {"evidence": []}


def test_document_evidence_alone_preserves_grounded_mode():
    """Upload evidence with zero web hits is still grounding — don't downgrade."""
    out = _research_result({"mode": "hybrid", "_job_id": ""}, [_evidence("file://doc.pdf#p1")])
    assert "mode" not in out


# ---------------------------------------------------------------------------
# research_node — the wiring
# ---------------------------------------------------------------------------


def test_research_node_downgrades_when_every_search_returns_nothing():
    """The 'no raw results' early-return path must go through the gate."""
    state = {
        "topic": "How photosynthesis works",
        "mode": "hybrid",
        "queries": ["how photosynthesis works"],
        "recency_days": 3650,
        "_job_id": "",
    }
    with patch.object(research_mod, "_tavily_search", return_value=[]):
        out = research_node(state)

    assert out["evidence"] == []
    assert out["mode"] == "closed_book"
    assert out["needs_research"] is False
