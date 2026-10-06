"""Regression tests for the on-demand manual task handlers.

These cover the state a handler rebuilds from disk, which is not the state the
graph had in memory: anything a node reads from state but the rebuild omits
silently degrades the output instead of raising.
"""

import json
import threading
from pathlib import Path

import Graph.nodes as nodes
import api.manual_tasks as manual_tasks
from api.manual_tasks import ManualTaskContext, _load_evidence

EVIDENCE = [
    {"url": "https://example.com/a", "fact": "A cited fact.", "source": "Example"},
]


def _make_context(tmp_path: Path, task_name: str, state: dict) -> ManualTaskContext:
    """Build a context over a job folder whose evidence is on disk but not in state."""
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research" / "evidence.json").write_text(json.dumps(EVIDENCE), encoding="utf-8")
    return ManualTaskContext(
        job_id="job-1",
        task_name=task_name,
        job={"topic": "Test topic"},
        base_path=tmp_path,
        meta_path=tmp_path / "metadata" / "metadata.json",
        state=state,
        plan=None,
        job_lock=threading.Lock(),
        pipeline_loader=lambda: None,
    )


def _silence_persistence(monkeypatch) -> None:
    monkeypatch.setattr(manual_tasks, "update_job", lambda *a, **k: None)
    monkeypatch.setattr(manual_tasks, "_update_metadata_json", lambda *a, **k: None)
    monkeypatch.setattr(manual_tasks, "_write_deepeval_report", lambda *a, **k: None)
    monkeypatch.setattr(manual_tasks, "_save_content", lambda context: {})
    monkeypatch.setattr(manual_tasks.events, "emit", lambda *a, **k: None)


def test_manual_qa_rerun_receives_the_jobs_evidence(tmp_path: Path, monkeypatch):
    """A QA re-run used to rebuild state with no evidence pool. Every link in the
    article then failed the citation verifier, the verdict flipped to
    NEEDS_REVISION, and the revision pass stripped the citations out of a
    grounded article before overwriting final_content with the result."""
    seen = {}

    def fake_qa(state):
        seen["evidence"] = state.get("evidence")
        return {"qa_verdict": "READY", "qa_score": 9.0, "final": state.get("final")}

    monkeypatch.setattr(nodes, "qa_agent_node", fake_qa)
    _silence_persistence(monkeypatch)

    context = _make_context(tmp_path, "qa", {"final": "# Post\n\nA fact [1](https://example.com/a)."})
    manual_tasks._handle_content_task(context)

    assert seen["evidence"] == EVIDENCE


def test_deepeval_still_receives_evidence(tmp_path: Path, monkeypatch):
    """Guards the shared loader: deepeval loaded evidence inline before the refactor."""
    seen = {}

    def fake_deepeval(state):
        seen["evidence"] = state.get("evidence")
        return {"deepeval_scores": {"overall_score": 0.8}}

    monkeypatch.setattr(nodes, "deepeval_evaluation_node", fake_deepeval)
    _silence_persistence(monkeypatch)

    context = _make_context(tmp_path, "deepeval", {"final": "# Post"})
    manual_tasks._handle_deepeval(context)

    assert seen["evidence"] == EVIDENCE


def test_load_evidence_is_empty_when_the_job_was_never_grounded(tmp_path: Path):
    assert _load_evidence(tmp_path) == []


def test_load_evidence_rejects_a_non_list_payload(tmp_path: Path):
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research" / "evidence.json").write_text('{"not": "a list"}', encoding="utf-8")

    assert _load_evidence(tmp_path) == []
