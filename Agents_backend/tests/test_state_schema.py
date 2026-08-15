"""Guards the contract between the API's initial state and the graph schema.

LangGraph silently DROPS any key passed to the graph that is not declared in
the State TypedDict. That is not an error and produces no warning — the node
just reads back the `.get()` default forever.

This is not hypothetical: `generate_qa` was sent by the API but never declared
in State, so `completion_validator`'s conditional edge always took the `else`
branch and the QA agent + revision loop never executed for a single web run.
`selected_model` and `target_audience` were dropped the same way, which made
the UI's model selector and audience field decorative.

If you add a key to initial_state, declare it in State. These tests fail loudly
if you don't.
"""

from Graph.state import State
from api.background import build_initial_state
from api.schemas import GenerationConfig


def test_langgraph_drops_undeclared_state_keys():
    """Documents WHY the test below matters — this is the trap being guarded."""
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END

    class TinyState(TypedDict, total=False):
        declared: str

    seen: dict = {}

    def node(s):
        seen.update(s)
        return {}

    g = StateGraph(TinyState)
    g.add_node("node", node)
    g.add_edge(START, "node")
    g.add_edge("node", END)
    g.compile().invoke({"declared": "kept", "undeclared": "silently dropped"})

    assert "declared" in seen
    assert "undeclared" not in seen, "LangGraph now preserves unknown keys — relax this guard"


def test_every_initial_state_key_is_declared_in_the_graph_schema():
    initial_state = build_initial_state(
        job_id="job-1",
        topic="Test topic",
        blog_folder="/tmp/blog",
        generation_config=GenerationConfig(),
    )

    undeclared = set(initial_state) - set(State.__annotations__)
    assert not undeclared, (
        f"These keys are sent to the graph but not declared in State, so LangGraph "
        f"will silently drop them: {sorted(undeclared)}"
    )


def test_generate_qa_reaches_the_graph():
    """The specific regression: QA must be togglable, and ON by default."""
    assert "generate_qa" in State.__annotations__
    assert GenerationConfig().generate_qa is True
    assert build_initial_state("j", "t", "/tmp", GenerationConfig())["generate_qa"] is True
    assert build_initial_state(
        "j", "t", "/tmp", GenerationConfig(generate_qa=False)
    )["generate_qa"] is False


def test_qa_flag_survives_a_real_graph_round_trip():
    """End-to-end proof against the real State, not a stand-in.

    This is the assertion that would have failed before the fix: the node saw
    `generate_qa` missing, so `s.get("generate_qa", False)` sent every run
    straight past the QA agent to the keyword optimizer.
    """
    from langgraph.graph import StateGraph, START, END

    routed_to = []

    def completion_validator(s):
        # Same predicate as the conditional edge in main.py::build_graph
        routed_to.append("qa_agent" if s.get("generate_qa", False) else "keyword_optimizer")
        return {}

    g = StateGraph(State)
    g.add_node("completion_validator", completion_validator)
    g.add_edge(START, "completion_validator")
    g.add_edge("completion_validator", END)
    app = g.compile()

    app.invoke(build_initial_state("j", "Topic", "/tmp", GenerationConfig()))
    app.invoke(build_initial_state("j", "Topic", "/tmp", GenerationConfig(generate_qa=False)))

    assert routed_to == ["qa_agent", "keyword_optimizer"]
