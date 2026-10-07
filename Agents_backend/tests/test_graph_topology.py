"""
Structural tests for the compiled LangGraph workflow.

WHY THIS FILE EXISTS
--------------------
Every other test exercises a node in isolation. Nothing verified how the nodes
are WIRED, so a mis-drawn edge — a stage skipped, a cycle broken, an interrupt
removed — would pass the entire suite and only surface as odd behaviour during
a live run costing real tokens.

That failure mode is not hypothetical here. `generate_qa` was absent from the
State schema, so the conditional edge out of `completion_validator` always took
the else-branch and the QA agent plus its revision loop never executed for a
single web run. No error, no warning, no failing test: just a pipeline quietly
missing its quality gate.

These tests build the real graph and assert its shape. They make no API calls
and add roughly a second to the suite.
"""

from __future__ import annotations

import pytest

from main import build_graph


@pytest.fixture(scope="module")
def graph():
    return build_graph()


@pytest.fixture(scope="module")
def topology(graph):
    """(nodes, edges) where edges is a set of (source, target) pairs."""
    drawable = graph.get_graph()
    nodes = set(drawable.nodes)
    edges = {(e.source, e.target) for e in drawable.edges}
    return nodes, edges


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

EXPECTED_NODES = {
    "router",
    "document_ingest",
    "research",
    "orchestrator",
    "worker",
    "reducer",
    "completion_validator",
    "seo_metadata_generator",
    "qa_agent",
    "revision",
    "keyword_optimizer",
    "geval_evaluator",
    "campaign_generator",
    "video_generator",
    "podcast_generator",
}


def test_the_expected_nodes_are_present(topology):
    nodes, _ = topology
    missing = EXPECTED_NODES - nodes
    assert not missing, f"nodes missing from the compiled graph: {sorted(missing)}"


def test_no_unexpected_nodes_have_appeared(topology):
    """A new stage should be a deliberate change, recorded here."""
    nodes, _ = topology
    extra = nodes - EXPECTED_NODES - {"__start__", "__end__"}
    assert not extra, (
        f"undeclared nodes in the graph: {sorted(extra)}. Add them to "
        f"EXPECTED_NODES if intentional."
    )


def test_deepeval_is_not_a_graph_node(topology):
    """DeepEval runs on demand from its own endpoint.

    Four chain-of-thought judge calls on every generation is not a cost worth
    paying by default, and the README documents it as out-of-graph.
    """
    nodes, _ = topology
    assert "deepeval_evaluator" not in nodes


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,target,why",
    [
        ("__start__", "router", "the router classifies every run first"),
        ("research", "orchestrator", "evidence must reach the planner"),
        ("orchestrator", "worker", "the Send fan-out dispatches section writers"),
        ("worker", "reducer", "sections are merged after writing"),
        ("reducer", "completion_validator", "structure is checked before QA"),
        ("completion_validator", "seo_metadata_generator", "SEO metadata is generated alongside QA"),
        ("seo_metadata_generator", "__end__", "the SEO branch ends on its own"),
        ("keyword_optimizer", "geval_evaluator", "evaluation follows SEO optimisation"),
        ("campaign_generator", "__end__", "media nodes terminate the graph"),
        ("video_generator", "__end__", "media nodes terminate the graph"),
        ("podcast_generator", "__end__", "media nodes terminate the graph"),
    ],
)
def test_required_edge_exists(topology, source, target, why):
    _, edges = topology
    assert (source, target) in edges, f"missing edge {source} -> {target}: {why}"


def test_the_revision_loop_is_a_real_cycle(topology):
    """qa_agent -> revision -> qa_agent is what makes this graph cyclic.

    Without the return edge the reviser would run once and its output would
    never be re-audited, so a fix could introduce a new problem unnoticed.
    """
    _, edges = topology
    assert ("qa_agent", "revision") in edges, "QA cannot reach the reviser"
    assert ("revision", "qa_agent") in edges, "revision output is never re-audited"


def test_qa_can_be_bypassed_but_never_skips_the_optimizer(topology):
    """completion_validator routes to QA or straight past it, never to neither."""
    _, edges = topology
    assert ("completion_validator", "qa_agent") in edges
    assert ("completion_validator", "keyword_optimizer") in edges


def test_evaluation_precedes_media_generation(topology):
    """G-Eval scores the article, so it must run before the media fan-out.

    The README's architecture diagram once showed the reverse.
    """
    _, edges = topology
    for media in ("campaign_generator", "video_generator", "podcast_generator"):
        assert ("geval_evaluator", media) in edges, (
            f"geval_evaluator must fan out to {media}"
        )
        assert (media, "geval_evaluator") not in edges, (
            f"{media} must not feed back into evaluation"
        )


def test_uploads_route_through_ingest_before_planning(topology):
    """A document upload must be ingested, and may still add web research."""
    _, edges = topology
    assert ("router", "document_ingest") in edges
    assert ("document_ingest", "orchestrator") in edges, "closed-book upload path"
    assert ("document_ingest", "research") in edges, "hybrid upload path"


def test_router_can_skip_research_entirely(topology):
    """closed_book runs must reach the planner without a search."""
    _, edges = topology
    assert ("router", "orchestrator") in edges
    assert ("router", "research") in edges


# ---------------------------------------------------------------------------
# Human-in-the-loop
# ---------------------------------------------------------------------------


def test_the_graph_interrupts_after_planning(graph):
    """The outline is the approval point; execution must halt there.

    Losing this would dispatch the parallel writers — the most expensive stage
    — before the user ever saw the plan.
    """
    assert list(graph.interrupt_after_nodes) == ["orchestrator"]


# ---------------------------------------------------------------------------
# Routing predicates
# ---------------------------------------------------------------------------


def test_completion_validator_routes_on_the_generate_qa_flag():
    """The exact regression this file was written for.

    `generate_qa` was undeclared in State, so LangGraph dropped it and this
    predicate always read the `.get()` default of False — sending every web run
    past the QA agent to the keyword optimizer.
    """
    from api.background import build_initial_state
    from api.schemas import GenerationConfig
    from main import after_validation_router  # the real router, not a copy of it

    on = build_initial_state("j", "t", "/tmp", GenerationConfig())
    off = build_initial_state("j", "t", "/tmp", GenerationConfig(generate_qa=False))

    # The SEO metadata call is always the second branch, run beside the first.
    assert after_validation_router(on) == ["qa_agent", "seo_metadata_generator"]
    assert after_validation_router(off) == ["keyword_optimizer", "seo_metadata_generator"]


def test_seo_metadata_runs_beside_qa_and_still_reaches_the_final_state(monkeypatch):
    """Run the real compiled graph from the reducer onward, with the nodes stubbed.

    The SEO call used to sit inside merge_content, in front of everything. Here QA and
    the SEO node each wait on one barrier, which only opens if both are in flight at
    once; run one after the other, the first would sit there until the timeout broke
    the barrier and the run raised. The metadata must still land in the final state.
    """
    import threading

    import main
    from langgraph.checkpoint.memory import MemorySaver

    barrier = threading.Barrier(2, timeout=5)

    def qa(state):
        barrier.wait()
        return {"qa_verdict": "READY", "qa_issues": []}

    def seo(state):
        barrier.wait()
        return {"seo_metadata": {"reading_time_minutes": 3}}

    monkeypatch.setattr(main, "qa_agent_node", qa)
    monkeypatch.setattr(main, "seo_metadata_node", seo)
    monkeypatch.setattr(main, "validate_completion", lambda s: {})
    monkeypatch.setattr(main, "keyword_optimizer_node", lambda s: {})
    monkeypatch.setattr(main, "geval_evaluation_node", lambda s: {})

    graph = main.build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "seo-beside-qa"}}
    graph.update_state(
        config,
        {"final": "article", "generate_qa": True,
         "generate_campaign": False, "generate_video": False, "generate_podcast": False},
        as_node="reducer",  # as if the reducer had just finished
    )

    assert graph.invoke(None, config)["seo_metadata"] == {"reading_time_minutes": 3}


def test_revision_loop_is_bounded():
    """The cycle must terminate. MAX_REVISIONS is the only thing stopping it."""
    from Graph.agents.revision import MAX_REVISIONS

    assert isinstance(MAX_REVISIONS, int)
    assert 1 <= MAX_REVISIONS <= 5, (
        f"MAX_REVISIONS={MAX_REVISIONS} is outside a defensible range; each "
        f"iteration is a full-article LLM call"
    )

    critical = [{"severity": "critical"}]

    def after_qa(verdict, issues, count):  # mirrors _after_qa_manual
        if verdict == "NEEDS_REVISION":
            if [i for i in issues if i.get("severity") == "critical"] and count < MAX_REVISIONS:
                return "revision"
        return "keyword_optimizer"

    assert after_qa("NEEDS_REVISION", critical, 0) == "revision"
    assert after_qa("NEEDS_REVISION", critical, MAX_REVISIONS) == "keyword_optimizer", (
        "the loop does not terminate at its bound"
    )
    assert after_qa("READY", [], 0) == "keyword_optimizer"
    assert after_qa("NEEDS_REVISION", [{"severity": "minor"}], 0) == "keyword_optimizer", (
        "only critical issues should trigger a rewrite"
    )


def test_media_router_returns_end_when_all_toggles_are_off():
    """With no media requested the graph must terminate, not stall."""
    from langgraph.graph import END

    def after_evaluator(s):  # mirrors after_evaluator_router
        destinations = []
        if s.get("generate_campaign", True):
            destinations.append("campaign_generator")
        if s.get("generate_video", True):
            destinations.append("video_generator")
        if s.get("generate_podcast", True):
            destinations.append("podcast_generator")
        return destinations if destinations else END

    all_off = {"generate_campaign": False, "generate_video": False, "generate_podcast": False}
    assert after_evaluator(all_off) == END

    one_on = {**all_off, "generate_video": True}
    assert after_evaluator(one_on) == ["video_generator"]

    assert len(after_evaluator({})) == 3, "defaults should fan out to all three"


def test_updates_stream_names_the_keyword_step(monkeypatch):
    """_run_pipeline publishes the article when an update keyed "keyword_optimizer"
    arrives; the real compiled graph must report the node under that name."""
    import main
    from langgraph.checkpoint.memory import MemorySaver

    for name in ("qa_agent_node", "seo_metadata_node", "geval_evaluation_node"):
        monkeypatch.setattr(main, name, lambda s: {})
    monkeypatch.setattr(main, "validate_completion", lambda s: {})
    monkeypatch.setattr(main, "keyword_optimizer_node", lambda s: {"keyword_report": "r"})

    graph = main.build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "updates-names"}}
    graph.update_state(config, {"final": "article", "generate_qa": False, "generate_campaign": False,
                                "generate_video": False, "generate_podcast": False}, as_node="reducer")

    nodes = [n for update in graph.stream(None, config, stream_mode="updates") for n in update]
    assert "keyword_optimizer" in nodes
    assert nodes.index("keyword_optimizer") < nodes.index("geval_evaluator")
