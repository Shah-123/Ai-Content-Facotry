"""
Tests for event_bus.py — real-time event pub/sub system.

Tests the synchronous, non-asyncio parts of the event bus:
emit, get_history, clear_job, and AgentEvent.

Note: event_bus.py persists events to disk as JSONL files under
data/events/<job_id>.jsonl. Each test gets a unique job_id and
explicitly clears it on teardown to keep the suite hermetic.
"""
import pytest
from event_bus import (
    AgentEvent,
    emit,
    get_history,
    clear_job,
    _subscribers,
)


@pytest.fixture(autouse=True)
def clean_event_bus():
    """Ensure each test starts with a clean event bus."""
    _subscribers.clear()
    yield
    _subscribers.clear()


# ========================================================================
# AgentEvent
# ========================================================================

class TestAgentEvent:
    """Tests for the AgentEvent dataclass."""

    def test_to_dict(self):
        event = AgentEvent(
            job_id="job1", agent_name="router", status="started",
            message="Analyzing topic", timestamp=1000.0
        )
        d = event.to_dict()
        assert d["job_id"] == "job1"
        assert d["agent_name"] == "router"
        assert d["metrics"] == {}  # None → {}

    def test_to_dict_with_metrics(self):
        event = AgentEvent(
            job_id="job1", agent_name="qa", status="completed",
            message="Done", timestamp=1000.0, metrics={"score": 8.5}
        )
        d = event.to_dict()
        assert d["metrics"] == {"score": 8.5}


# ========================================================================
# emit + get_history
# ========================================================================

# Unique job_id per test method so concurrent test runs don't collide.
import uuid


def _job_id(prefix: str) -> str:
    return f"test_{prefix}_{uuid.uuid4().hex[:8]}"


class TestEmitAndHistory:
    """Tests for emit() and get_history() (disk-backed JSONL)."""

    def test_emit_stores_event_in_history(self):
        jid = _job_id("emit_one")
        try:
            emit(jid, "router", "started", "Starting analysis")
            history = get_history(jid)
            assert len(history) == 1
            assert history[0]["agent_name"] == "router"
            assert history[0]["message"] == "Starting analysis"
        finally:
            clear_job(jid)

    def test_multiple_emits_accumulate(self):
        jid = _job_id("emit_many")
        try:
            emit(jid, "router", "started", "Step 1")
            emit(jid, "researcher", "started", "Step 2")
            emit(jid, "qa", "completed", "Step 3")
            history = get_history(jid)
            assert len(history) == 3
        finally:
            clear_job(jid)

    def test_separate_jobs_have_separate_history(self):
        jid_a = _job_id("sep_a")
        jid_b = _job_id("sep_b")
        try:
            emit(jid_a, "router", "started", "Job A event")
            emit(jid_b, "router", "started", "Job B event")
            assert len(get_history(jid_a)) == 1
            assert len(get_history(jid_b)) == 1
        finally:
            clear_job(jid_a)
            clear_job(jid_b)

    def test_empty_job_id_is_skipped(self):
        # emit() returns early when job_id is falsy — no file is written.
        emit("", "router", "started", "Should be skipped")
        assert get_history("") == []


# ========================================================================
# clear_job
# ========================================================================

class TestClearJob:
    """Tests for clear_job() — should remove the on-disk JSONL file."""

    def test_clears_history(self):
        jid = _job_id("clear_history")
        emit(jid, "agent", "started", "Something")
        assert len(get_history(jid)) == 1
        clear_job(jid)
        assert get_history(jid) == []

    def test_no_error_on_nonexistent_job(self):
        clear_job("nonexistent_" + uuid.uuid4().hex[:8])  # should not raise
