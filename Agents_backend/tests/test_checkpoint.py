import sqlite3
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from typing import TypedDict


class SimpleState(TypedDict):
    count: int
    topic: str


def increment_node(state: SimpleState) -> dict:
    return {"count": state.get("count", 0) + 1}


def test_sqlite_saver_lifecycle():
    # 1. Setup in-memory sqlite connection
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        memory = SqliteSaver(conn)
        memory.setup()

        # Check that setup() successfully created the checkpoint tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert "checkpoints" in tables
        assert "writes" in tables

        # 2. Build a simple state graph with an interrupt
        workflow = StateGraph(SimpleState)
        workflow.add_node("step1", increment_node)
        workflow.add_node("step2", increment_node)
        workflow.add_edge(START, "step1")
        workflow.add_edge("step1", "step2")
        workflow.add_edge("step2", END)

        # Compile graph with interrupt_after="step1"
        graph = workflow.compile(checkpointer=memory, interrupt_after=["step1"])

        # 3. First run: should execute step1 and then stop
        thread_cfg = {"configurable": {"thread_id": "test_job_123"}}
        initial_state = {"count": 10, "topic": "AI Checkpointing"}

        events = list(graph.stream(initial_state, thread_cfg, stream_mode="values"))
        assert len(events) > 0

        # Verify state stopped at step1
        state = graph.get_state(thread_cfg)
        assert state.next == ("step2",)
        assert state.values["count"] == 11
        assert state.values["topic"] == "AI Checkpointing"

        # 4. Resume run: pass None to graph.stream to resume from the step1 checkpoint
        resume_events = list(graph.stream(None, thread_cfg, stream_mode="values"))
        assert len(resume_events) > 0

        # Verify state reached END and count was incremented again by step2
        final_state = graph.get_state(thread_cfg)
        assert final_state.next == ()
        assert final_state.values["count"] == 12

    finally:
        conn.close()
