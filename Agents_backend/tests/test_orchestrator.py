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


# ---------------------------------------------------------------------------
# Ablation switch — the control arm for the evidence-distribution experiment
# ---------------------------------------------------------------------------


class TestAblationSwitch:
    """`assign_evidence=False` must reproduce the pre-fix behaviour exactly.

    The control arm is only valid if turning the flag off genuinely hands every
    worker the full evidence pool. That relies on two things holding together:
    the orchestrator must skip assignment, and the worker-side slicing must fall
    back to the full list when no indices were assigned.
    """

    def test_flag_is_declared_in_state_and_defaults_on(self):
        from Graph.state import State
        from api.schemas import GenerationConfig

        assert "assign_evidence" in State.__annotations__
        assert GenerationConfig().assign_evidence is True

    def test_flag_reaches_the_graph_state(self):
        from api.background import build_initial_state
        from api.schemas import GenerationConfig

        on = build_initial_state("j", "t", "/tmp", GenerationConfig())
        off = build_initial_state(
            "j", "t", "/tmp", GenerationConfig(assign_evidence=False)
        )
        assert on["assign_evidence"] is True
        assert off["assign_evidence"] is False

    def test_unassigned_plan_falls_back_to_the_full_pool(self):
        """With no indices assigned, each worker must receive every item."""
        from Graph.agents.workers import _get_assigned_evidence_dicts

        plan = _make_plan(4)
        evidence = _make_evidence(6)
        dicts = [e.model_dump() for e in evidence]

        # Control arm: _assign_evidence_to_tasks was never called, so every
        # task still carries the empty default.
        for task in plan.tasks:
            assert task.assigned_evidence_indices == []
            assert len(_get_assigned_evidence_dicts(task, dicts)) == len(dicts)

    def test_assigned_plan_gives_each_worker_a_strict_subset(self):
        """Treatment arm: slices must be smaller than the full pool."""
        from Graph.agents.workers import _get_assigned_evidence_dicts

        plan = _make_plan(4)
        evidence = _make_evidence(12)
        dicts = [e.model_dump() for e in evidence]
        _assign_evidence_to_tasks(plan, evidence)

        for task in plan.tasks:
            got = _get_assigned_evidence_dicts(task, dicts)
            assert 0 < len(got) < len(dicts), (
                f"task {task.id} received {len(got)} of {len(dicts)} items — "
                f"the treatment arm must partition, not hand over everything"
            )

    def test_the_two_arms_actually_differ(self):
        """Guards against an ablation that silently measures nothing."""
        from Graph.agents.workers import _get_assigned_evidence_dicts

        evidence = _make_evidence(12)
        dicts = [e.model_dump() for e in evidence]

        control = _make_plan(4)
        treatment = _assign_evidence_to_tasks(_make_plan(4), evidence)

        control_sizes = [len(_get_assigned_evidence_dicts(t, dicts)) for t in control.tasks]
        treat_sizes = [len(_get_assigned_evidence_dicts(t, dicts)) for t in treatment.tasks]
        assert control_sizes != treat_sizes, "both arms behave identically"
        assert sum(treat_sizes) < sum(control_sizes)
