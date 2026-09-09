"""
render_results_tables.py — Generate the Chapter 5 results tables from artefacts.

The results tables were originally typed by hand from summary.json files. That
is a transcription step, and a transcription step is a place for a number to
drift from the run that produced it. This renders the LaTeX bodies directly
from the artefacts on disk, so the thesis and the evidence cannot disagree.

Usage (from Agents_backend/):
    python -m tests.golden.render_results_tables            # all arms
    python -m tests.golden.render_results_tables --arm assigned
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_RUNS = Path(__file__).parent / "_runs"

# Fixture id -> the label used in the thesis
_LABELS = {
    "closed_book_evergreen": "Evergreen (photosynthesis)",
    "hybrid_evergreen_tech": "Professional (SEO 2026)",
    "open_book_current": "Technical (multi-agent AI)",
}
_ORDER = list(_LABELS)


def load(arm: str | None) -> list[dict]:
    """Newest run per fixture, optionally restricted to one ablation arm.

    Artefacts predating the arm split live in `_runs/<case_id>/` with no `arm`
    key; the arms write to `_runs/<case_id>__<arm>/`. Both can be present at
    once, so keeping only the most recent run per fixture prevents a stale
    pre-fix result being tabled next to the run that superseded it.
    """
    best: dict[str, dict] = {}
    for f in sorted(_RUNS.glob("*/summary.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"% skipped unreadable {f}: {exc}")
            continue
        if arm is not None and d.get("arm") != arm:
            continue
        case = d.get("case_id", f.parent.name)
        prior = best.get(case)
        if prior is None or str(d.get("run_at", "")) > str(prior.get("run_at", "")):
            best[case] = d

    rows = list(best.values())
    rows.sort(key=lambda r: _ORDER.index(r["case_id"]) if r["case_id"] in _ORDER else 99)
    return rows


def _esc(s: str) -> str:
    return str(s).replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def main_table(rows: list[dict]) -> str:
    out = []
    for r in rows:
        label = _LABELS.get(r["case_id"], _esc(r["case_id"]))
        out.append(
            f"        {label} & {_esc(r.get('router_mode'))} & "
            f"{r.get('word_count', 0):,} & {r.get('evidence_count', 0)} & "
            f"{r.get('qa_score')} & {_esc(r.get('qa_verdict'))} & "
            f"{r.get('revision_count', 0)} & {r.get('geval_overall')} \\\\\n        \\hline"
        )
    return "\n".join(out)


def rubric_table(rows: list[dict]) -> str:
    dims = [
        ("Coherence (structure \\& flow)", "coherence", "30\\%"),
        ("Relevance (topic coverage)", "relevance", "20\\%"),
        ("Accuracy \\& grounding", "accuracy", "30\\%"),
        ("Tone alignment", "tone_alignment", "20\\%"),
    ]
    out = []
    for label, key, weight in dims:
        cells = " & ".join(str((r.get("geval") or {}).get(key, "--")) for r in rows)
        out.append(f"        {label} & {weight} & {cells} \\\\\n        \\hline")
    overall = " & ".join(f"\\textbf{{{r.get('geval_overall')}}}" for r in rows)
    out.append(f"        \\textbf{{Weighted overall}} & --- & {overall} \\\\\n        \\hline")
    return "\n".join(out)


def usage_summary(rows: list[dict]) -> str:
    priced = [r for r in rows if r.get("usage", {}).get("total")]
    if not priced:
        return "% no usage data recorded in these runs"
    lines = []
    for r in priced:
        t = r["usage"]["total"]
        lines.append(
            f"        {_LABELS.get(r['case_id'], _esc(r['case_id']))} & "
            f"{t['calls']} & {t['total_tokens']:,} & {t['cost_usd']:.4f} \\\\\n        \\hline"
        )
    n = len(priced)
    mean_cost = sum(r["usage"]["total"]["cost_usd"] for r in priced) / n
    mean_tok = sum(r["usage"]["total"]["total_tokens"] for r in priced) / n
    lines.append(
        f"        \\textbf{{Mean}} & --- & \\textbf{{{mean_tok:,.0f}}} & "
        f"\\textbf{{{mean_cost:.4f}}} \\\\\n        \\hline"
    )
    return "\n".join(lines)


# Evaluator input caps, mirrored from quality_control.py and evaluation.py.
_QA_LIMIT = 30_000
_GEVAL_LIMIT = 25_000


def coverage_notes(rows: list[dict]) -> str:
    """Which runs were graded on only part of their text.

    Computed from the saved article rather than read from summary.json: the
    harness records the four rubric scores but not the coverage record that
    sits alongside them in state, and the runs were already in flight when that
    gap was noticed. Recomputing from blog.md gives the same answer without
    altering the harness mid-experiment.
    """
    notes = []
    for r in rows:
        blog = _RUNS / f"{r['case_id']}__{r.get('arm', 'assigned')}" / "blog.md"
        if not blog.exists():
            blog = _RUNS / r["case_id"] / "blog.md"
        if not blog.exists():
            continue
        n = len(blog.read_text(encoding="utf-8"))
        if n > _GEVAL_LIMIT:
            notes.append(
                f"{_LABELS.get(r['case_id'], r['case_id'])}: {n:,} characters, "
                f"audited on {min(n, _QA_LIMIT) / n:.0%} and judged on "
                f"{min(n, _GEVAL_LIMIT) / n:.0%}"
            )
    return "; ".join(notes) or "every run was evaluated in full"


def repetition_caveats(rows: list[dict]) -> str:
    """Flag runs where the repetition rate rests on too few statistics.

    `repetition_rate` is repeated/distinct. When an article contains only one
    or two distinct statistics the rate can only take a handful of values — a
    single reused figure reads as 1.0, which is indistinguishable from an
    article that repeats everything. Such runs must not be pooled into a mean
    without saying so; report the raw counts and max_section_spread instead.
    """
    weak = []
    for r in rows:
        rep = r.get("repetition") or {}
        distinct = rep.get("distinct_statistics", 0)
        if 0 < distinct < 5:
            weak.append(
                f"{_LABELS.get(r['case_id'], r['case_id'])} "
                f"(rate {rep.get('repetition_rate')} from only {distinct} distinct "
                f"statistic{'s' if distinct != 1 else ''})"
            )
        elif distinct == 0:
            weak.append(
                f"{_LABELS.get(r['case_id'], r['case_id'])} (no statistics found; "
                f"rate is undefined and reported as 0.0)"
            )
    return "; ".join(weak) or "all runs had a sufficient statistic count"


def ablation_table() -> tuple[str, str]:
    """Per-fixture and aggregate comparison of the two evidence-distribution arms.

    Returns (per_fixture_rows, summary_line).

    `max_section_spread` leads because it needs no denominator. The repetition
    RATE is repeated/distinct, and an article containing one or two distinct
    figures can only score 0.0 or 1.0 — the evergreen fixture scores 1.0 in
    both arms purely because it has so few statistics, which says nothing about
    the treatment. The spread is the count of sections the single most-reused
    statistic reaches, and it separates the arms cleanly.
    """
    treat = {r["case_id"]: r for r in load("assigned")}
    ctrl = {r["case_id"]: r for r in load("fullpool")}

    rows, t_spreads, c_spreads, t_rep, c_rep = [], [], [], [], []
    for case in _ORDER:
        t, c = treat.get(case), ctrl.get(case)
        if not t or not c:
            continue
        tr, cr = t["repetition"], c["repetition"]
        rows.append(
            f"        {_LABELS[case]} & {cr['max_section_spread']} & "
            f"{tr['max_section_spread']} & {cr['repeated_statistics']} & "
            f"{tr['repeated_statistics']} \\\\\n        \\hline"
        )
        t_spreads.append(tr["max_section_spread"])
        c_spreads.append(cr["max_section_spread"])
        t_rep.append(tr["repeated_statistics"])
        c_rep.append(cr["repeated_statistics"])

    if not rows:
        return "% both arms required — run GOLDEN_ASSIGN_EVIDENCE=0 and =1", ""

    n = len(rows)
    rows.append(
        f"        \\textbf{{Mean}} & \\textbf{{{sum(c_spreads)/n:.1f}}} & "
        f"\\textbf{{{sum(t_spreads)/n:.1f}}} & \\textbf{{{sum(c_rep)/n:.1f}}} & "
        f"\\textbf{{{sum(t_rep)/n:.1f}}} \\\\\n        \\hline"
    )
    summary = (
        f"n={n} per arm; worst-case spread {sum(c_spreads)/n:.1f} -> "
        f"{sum(t_spreads)/n:.1f}, repeated statistics {sum(c_rep)/n:.1f} -> "
        f"{sum(t_rep)/n:.1f}"
    )
    return "\n".join(rows), summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default=None, help="assigned | fullpool")
    args = ap.parse_args()

    rows = load(args.arm)
    if not rows:
        print("% no summary.json found — run the golden harness first")
        return 1

    print(f"% Generated from {len(rows)} run(s) in tests/golden/_runs/")
    for r in rows:
        print(f"%   {r['case_id']}  arm={r.get('arm','?')}  "
              f"writer={r.get('writer_model')}  judge={r.get('judge_model')}  "
              f"run_at={r.get('run_at')}")

    print("\n% ---- tab:golden_results ----")
    print(main_table(rows))
    print("\n% ---- tab:geval_breakdown ----")
    print(rubric_table(rows))
    print("\n% ---- token usage ----")
    print(usage_summary(rows))

    print("\n% ---- tab:ablation ----")
    abl, abl_summary = ablation_table()
    print(abl)
    if abl_summary:
        print(f"% {abl_summary}")

    print("\n% ---- notes for the threats-to-validity section ----")
    print(f"% truncation: {coverage_notes(rows)}")
    print(f"% repetition denominators: {repetition_caveats(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
