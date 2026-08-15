"""Router decision handling, including the forced-research query fallback."""

from unittest.mock import patch

from Graph.agents import routing
from Graph.state import RouterDecision


def _run_router(decision: RouterDecision, state: dict) -> dict:
    """Invoke router_node with the LLM's structured decision stubbed out."""
    class _FakeStructured:
        def invoke(self, _messages):
            return decision

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    with patch.object(routing, "llm", _FakeLLM()):
        return routing.router_node(state)


def test_forced_research_without_queries_falls_back_to_the_topic():
    """Regression: hybrid source_mode + a closed-book LLM verdict = 0 searches.

    source_mode defaults to "hybrid" for every web job, which forces
    needs_research=True. But a closed_book decision carries an EMPTY queries
    list, so research_node ran zero searches and silently produced no
    evidence while the UI still reported "hybrid" mode.
    """
    decision = RouterDecision(
        needs_research=False,
        mode="closed_book",
        reason="Evergreen topic, no research needed",
        queries=[],
    )
    out = _run_router(decision, {"topic": "How photosynthesis works", "source_mode": "hybrid"})

    assert out["needs_research"] is True
    assert out["mode"] == "hybrid"
    assert out["queries"], "forced research must never run with zero queries"
    assert out["queries"] == ["How photosynthesis works"]


def test_llm_supplied_queries_are_preserved():
    decision = RouterDecision(
        needs_research=True,
        mode="open_book",
        reason="Time-sensitive topic",
        queries=["latest multi-agent AI systems", "LangGraph 2026 release"],
    )
    out = _run_router(decision, {"topic": "Multi-agent AI", "source_mode": "hybrid"})

    assert out["queries"] == ["latest multi-agent AI systems", "LangGraph 2026 release"]
    assert out["mode"] == "open_book"
    assert out["recency_days"] == 7  # open_book uses the breaking-news window


def test_closed_book_source_mode_does_not_fabricate_queries():
    """An explicit closed_book request must stay closed-book — no searching."""
    decision = RouterDecision(
        needs_research=True, mode="open_book", reason="wants research", queries=["x"]
    )
    out = _run_router(decision, {"topic": "My uploaded document", "source_mode": "closed_book"})

    assert out["needs_research"] is False
    assert out["mode"] == "closed_book"
    assert out["recency_days"] == 3650
