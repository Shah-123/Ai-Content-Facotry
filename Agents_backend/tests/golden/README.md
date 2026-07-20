# Golden Tests — End-to-End Pipeline Regression

Curated topic fixtures that run the **entire** LangGraph pipeline and verify the output stays within documented quality bounds.

## When to run them

These tests **skip by default** because they:

- Cost real OpenAI + Tavily API tokens
- Take 1–3 minutes per topic to complete
- Require the same `.env` keys as a normal run

Run them when you've changed a prompt, a graph edge, or an agent and want confidence you haven't broken end-to-end behaviour.

## How to run

From the `Agents_backend/` directory, with the virtualenv activated:

```powershell
# Windows PowerShell
$env:RUN_GOLDEN_TESTS=1
pytest tests/golden -v -s
```

```bash
# bash / zsh
RUN_GOLDEN_TESTS=1 pytest tests/golden -v -s
```

Filter to a single topic:

```powershell
$env:RUN_GOLDEN_TESTS=1; pytest tests/golden -k closed_book_evergreen -v -s
```

## What's checked

For every case in `topics.json`, after the pipeline finishes the harness asserts:

| Field | Lower bound |
|---|---|
| `final` word count | `>= min_word_count` |
| `qa_score` | `>= min_qa_score` |
| `blog_evaluator_score` | `>= min_blog_evaluator_score` |
| `qa_verdict` | in `qa_verdict_in` allow-list |
| `len(evidence)` | `>= min_evidence_count` |
| Critical QA issues | `<= max_critical_issues` |
| Router `mode` | in `expected_mode_in` allow-list |

Bounds are deliberately permissive — the harness exists to catch **real regressions** (e.g. word count collapsing to 200, QA score dropping below 5, router misclassifying every topic), not score micro-fluctuations.

## Adding a new case

Append an object to `topics.json`:

```json
{
  "id": "your_short_slug",
  "topic": "The full topic prompt",
  "tone": "professional",
  "sections": 3,
  "expected": {
    "min_word_count": 1500,
    "min_qa_score": 6.5,
    "min_blog_evaluator_score": 6.5,
    "qa_verdict_in": ["READY", "NEEDS_REVISION"],
    "min_evidence_count": 2,
    "max_critical_issues": 2,
    "expected_mode_in": ["hybrid", "open_book"]
  }
}
```

The test harness picks it up automatically via `pytest.mark.parametrize`.

## Where outputs go

Each case writes its run artifacts to `tests/golden/_runs/<case_id>/` (gitignored). Inspect them after a failure to see what the pipeline actually produced.
