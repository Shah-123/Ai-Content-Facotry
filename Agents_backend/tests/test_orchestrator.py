"""
Tests for Graph/agents/orchestrator.py — evidence distribution algorithm.

_assign_evidence_to_tasks() is the key function that prevents all workers
from citing the same stats. It's pure (Plan in → Plan out, mutates in place).
"""
import pytest
from Graph.state import Plan, Task, EvidenceItem
from Graph.agents.orchestrator import _assign_evidence_to_tasks


def _make_task(task_id: int, title: str = "Test Section") -> Task:
    """Helper to create a minimal Task for testing."""
    return Task(
        id=task_id,
        title=f"{title} {task_id}",
        goal="Test goal",
        bullets=["Point 1"],
        target_words=300,
        tags=["test"],
    )


def _make_plan(n_tasks: int) -> Plan:
    """Helper to create a Plan with N tasks."""
    return Plan(
        blog_title="Test Blog",
        tone="professional",
        audience="testers",
        tasks=[_make_task(i) for i in range(n_tasks)],
    )


def _make_evidence(n: int) -> list:
    """Helper to create N dummy evidence items."""
    return [
        EvidenceItem(
            title=f"Source {i}",
            url=f"https://example.com/{i}",
            snippet=f"Evidence snippet {i}",
            published_at=None,
            source=f"source{i}.com",
        )
        for i in range(n)
    ]


class TestAssignEvidenceToTasks:
    """Tests for _assign_evidence_to_tasks()."""

    def test_assigns_indices_to_all_tasks(self):
        plan = _make_plan(4)
        evidence = _make_evidence(8)
        result = _assign_evidence_to_tasks(plan, evidence)
        for task in result.tasks:
            assert len(task.assigned_evidence_indices) > 0

    def test_indices_are_within_bounds(self):
        plan = _make_plan(6)
        evidence = _make_evidence(10)
        result = _assign_evidence_to_tasks(plan, evidence)
        for task in result.tasks:
            for idx in task.assigned_evidence_indices:
                assert 0 <= idx < len(evidence)

    def test_adjacent_sections_have_different_primary_source(self):
        """Adjacent sections should start from different evidence indices."""
        plan = _make_plan(4)
        evidence = _make_evidence(8)
        result = _assign_evidence_to_tasks(plan, evidence)
        for i in range(len(result.tasks) - 1):
            # First index of adjacent tasks should differ
            assert result.tasks[i].assigned_evidence_indices[0] != \
                   result.tasks[i + 1].assigned_evidence_indices[0]

    def test_handles_more_tasks_than_evidence(self):
        """When tasks > evidence, wraps around without crashing."""
        plan = _make_plan(8)
        evidence = _make_evidence(3)
        result = _assign_evidence_to_tasks(plan, evidence)
        for task in result.tasks:
            assert len(task.assigned_evidence_indices) > 0
            for idx in task.assigned_evidence_indices:
                assert 0 <= idx < len(evidence)

    def test_empty_evidence_returns_plan_unchanged(self):
        plan = _make_plan(4)
        result = _assign_evidence_to_tasks(plan, [])
        for task in result.tasks:
            assert task.assigned_evidence_indices == []

    def test_single_task(self):
        plan = _make_plan(1)
        evidence = _make_evidence(5)
        result = _assign_evidence_to_tasks(plan, evidence)
        assert len(result.tasks[0].assigned_evidence_indices) >= 1

    def test_single_evidence_item(self):
        plan = _make_plan(4)
        evidence = _make_evidence(1)
        result = _assign_evidence_to_tasks(plan, evidence)
        for task in result.tasks:
            assert task.assigned_evidence_indices == [0]

    def test_returns_same_plan_object(self):
        """The function mutates in place and returns the same Plan."""
        plan = _make_plan(3)
        evidence = _make_evidence(6)
        result = _assign_evidence_to_tasks(plan, evidence)
        assert result is plan
