"""
Golden Test Harness — End-to-End Pipeline Regression
=====================================================
Runs the full LangGraph pipeline against a curated list of topics and
asserts the output meets documented quality bounds (QA score, evidence
count, word count, etc.).

These tests:
  - Cost real API tokens (OpenAI + Tavily + optionally Gemini)
  - Take several minutes per topic to complete
  - Therefore skip by default — only run when explicitly enabled

Usage
-----
Run only the cheap unit tests (default):
    pytest

Run the golden harness explicitly:
    $env:RUN_GOLDEN_TESTS=1; pytest tests/golden -v -s

Or filter to a single topic:
    $env:RUN_GOLDEN_TESTS=1; pytest tests/golden -k closed_book_evergreen -v -s

What the harness checks
-----------------------
For each topic in `topics.json`, the harness runs the pipeline end-to-end
and asserts the final state satisfies the documented `expected` ranges:
  - min_word_count               — final blog must be at least N words
  - min_qa_score                 — QA agent score must clear floor
  - min_blog_evaluator_score     — independent reader-grade evaluator floor
  - qa_verdict_in                — verdict must be in this allow-list
  - min_evidence_count           — research must surface at least N citations
  - max_critical_issues          — at most N critical QA issues
  - expected_mode_in             — router must pick a mode in this list

These bounds are deliberately permissive so prompt tweaks don't cause
flaky failures — they exist to catch genuine regressions (e.g. word
count collapsing to 200, or QA score dropping below 5).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

# --- Skip the entire module unless explicitly opted in ---------------------
RUN_GOLDEN = os.getenv("RUN_GOLDEN_TESTS", "0") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_GOLDEN,
    reason=(
        "Golden tests cost real API tokens and take minutes per topic. "
        "Set RUN_GOLDEN_TESTS=1 to enable."
    ),
)

# --- Load the golden topic fixture once at module level --------------------
_GOLDEN_DIR = Path(__file__).parent
_TOPICS_FILE = _GOLDEN_DIR / "topics.json"

with _TOPICS_FILE.open("r", encoding="utf-8") as f:
    _GOLDEN = json.load(f)

_TOPIC_CASES = _GOLDEN["topics"]


# ===========================================================================
# Helpers
# ===========================================================================

def _build_initial_state(case: dict) -> dict:
    """Construct the initial graph state for a single golden topic."""
    return {
        "topic":             case["topic"],
        "as_of":             date.today().isoformat(),
        "sections":          [],
        "blog_folder":       str(_GOLDEN_DIR / "_runs" / case["id"]),
        "target_tone":       case.get("tone", "professional"),
        "target_keywords":   [],
        "target_sections":   case.get("sections", 3),
        "generate_images":   False,   # too slow / expensive for a regression run
        "generate_qa":       True,
        "generate_campaign": False,
        "generate_video":    False,
        "generate_podcast":  False,
        "export_formats":    [],
        "_job_id":           f"golden_{case['id']}",
    }


def _run_pipeline(case: dict) -> dict[str, Any]:
    """Run the full graph for one topic and return the terminal state values."""
    # Late imports so unit-test runs (which skip this module) never touch
    # langgraph / langchain heavy machinery.
    from main import build_graph
    import uuid as _uuid

    Path(case_state := _GOLDEN_DIR / "_runs" / case["id"]).mkdir(
        parents=True, exist_ok=True
    )

    app = build_graph()
    thread = {"configurable": {"thread_id": f"golden_{_uuid.uuid4().hex[:12]}"}}

    initial_state = _build_initial_state(case)

    # Phase 1: research + plan (graph interrupts after orchestrator for HITL)
    for _ in app.stream(initial_state, thread, stream_mode="values"):
        pass

    # Phase 2: auto-approve and run the rest
    for _ in app.stream(None, thread, stream_mode="values", recursion_limit=150):
        pass

    return app.get_state(thread).values


def _assert_within_bounds(case: dict, final_state: dict[str, Any]) -> list[str]:
    """
    Check the terminal state against the case's `expected` ranges.

    Returns a list of failure messages (empty list = all checks passed).
    Collecting failures instead of raising on the first one means a single
    pytest run surfaces every issue at once.
    """
    expected = case["expected"]
    failures: list[str] = []

    final = final_state.get("final", "")
    word_count = len(final.split())
    if word_count < expected["min_word_count"]:
        failures.append(
            f"word_count={word_count} < min_word_count={expected['min_word_count']}"
        )

    qa_score = final_state.get("qa_score") or 0
    if qa_score < expected["min_qa_score"]:
        failures.append(
            f"qa_score={qa_score} < min_qa_score={expected['min_qa_score']}"
        )

    eval_score = final_state.get("blog_evaluator_score") or 0
    if eval_score < expected["min_blog_evaluator_score"]:
        failures.append(
            f"blog_evaluator_score={eval_score} < "
            f"min_blog_evaluator_score={expected['min_blog_evaluator_score']}"
        )

    verdict = final_state.get("qa_verdict")
    if verdict not in expected["qa_verdict_in"]:
        failures.append(
            f"qa_verdict={verdict!r} not in {expected['qa_verdict_in']}"
        )

    evidence = final_state.get("evidence", [])
    if len(evidence) < expected["min_evidence_count"]:
        failures.append(
            f"evidence_count={len(evidence)} < "
            f"min_evidence_count={expected['min_evidence_count']}"
        )

    issues = final_state.get("qa_issues", [])
    critical = sum(1 for i in issues if i.get("severity") == "critical")
    if critical > expected["max_critical_issues"]:
        failures.append(
            f"critical_issues={critical} > "
            f"max_critical_issues={expected['max_critical_issues']}"
        )

    mode = final_state.get("mode")
    if mode not in expected["expected_mode_in"]:
        failures.append(
            f"router mode={mode!r} not in {expected['expected_mode_in']}"
        )

    return failures


# ===========================================================================
# Parametrized golden test
# ===========================================================================

@pytest.mark.parametrize(
    "case",
    _TOPIC_CASES,
    ids=[c["id"] for c in _TOPIC_CASES],
)
def test_golden_topic(case: dict) -> None:
    """
    Run the full pipeline for one golden topic and verify it stays within
    the documented quality bounds. Designed to catch genuine regressions
    (output collapse, prompt drift), not micro-fluctuations in scores.
    """
    final_state = _run_pipeline(case)

    # Diagnostic dump — printed when -s is used, stays silent otherwise
    print(
        f"\n[{case['id']}] "
        f"qa={final_state.get('qa_score')} "
        f"eval={final_state.get('blog_evaluator_score')} "
        f"words={len(final_state.get('final', '').split())} "
        f"evidence={len(final_state.get('evidence', []))} "
        f"verdict={final_state.get('qa_verdict')} "
        f"mode={final_state.get('mode')}"
    )

    failures = _assert_within_bounds(case, final_state)
    if failures:
        joined = "\n  - ".join(failures)
        pytest.fail(f"Golden bounds violated for '{case['id']}':\n  - {joined}")
