"""
report_ablation.py — Aggregate both ablation arms into a results table.

Reads every `summary.json` under `_runs/`, groups by arm, and prints a
comparison plus a LaTeX table body ready to paste into the results chapter.

Usage (from Agents_backend/):

    # 1. Treatment arm — evidence partitioned across workers (the fix)
    $env:RUN_GOLDEN_TESTS=1; $env:GOLDEN_ASSIGN_EVIDENCE=1
    pytest tests/golden -v -s

    # 2. Control arm — every worker receives the full pool (pre-fix behaviour)
    $env:RUN_GOLDEN_TESTS=1; $env:GOLDEN_ASSIGN_EVIDENCE=0
    pytest tests/golden -v -s

    # 3. Compare
    python -m tests.golden.report_ablation

Run each arm more than once per topic if you can afford it — a single run per
condition measures one sample of a stochastic generator, not an effect.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.golden.metrics import compare_arms

_RUNS = Path(__file__).parent / "_runs"


def load_runs() -> dict[str, list[dict]]:
    """Group every summary.json by ablation arm."""
    arms: dict[str, list[dict]] = {"assigned": [], "fullpool": []}
    for summary in sorted(_RUNS.glob("*/summary.json")):
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ! skipping unreadable {summary}: {exc}")
            continue
        arm = data.get("arm")
        if arm not in arms:
            # Pre-ablation artefacts have no 'arm' key; treat them as treatment
            # runs, since evidence distribution was already enabled by default.
            arm = "assigned"
        arms[arm].append(data)
    return arms


def _fmt(v) -> str:
    return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def main() -> int:
    arms = load_runs()
    on, off = arms["assigned"], arms["fullpool"]

    print("=" * 72)
    print("EVIDENCE-DISTRIBUTION ABLATION")
    print("=" * 72)
    print(f"treatment (evidence partitioned): {len(on)} run(s)")
    print(f"control   (full evidence pool)  : {len(off)} run(s)")

    if not on or not off:
        print("\nBoth arms are required for a comparison. Missing arm:",
              "control" if not off else "treatment")
        print("Re-run the harness with GOLDEN_ASSIGN_EVIDENCE=0 to collect it.")
        return 1

    print("\nPer-run detail")
    print("-" * 72)
    print(f"{'case':<26}{'arm':<11}{'rate':>7}{'repeat':>8}{'spread':>8}{'conc':>8}")
    for row in sorted(on + off, key=lambda r: (r["case_id"], r.get("arm", ""))):
        rep, src = row.get("repetition", {}), row.get("sources", {})
        print(f"{row['case_id'][:25]:<26}{row.get('arm','?'):<11}"
              f"{_fmt(rep.get('repetition_rate')):>7}"
              f"{_fmt(rep.get('repeated_statistics')):>8}"
              f"{_fmt(rep.get('max_section_spread')):>8}"
              f"{_fmt(src.get('concentration')):>8}")

    cmp = compare_arms(on, off)
    print("\nAggregate comparison (mean per arm)")
    print("-" * 72)
    print(f"{'metric':<28}{'partitioned':>13}{'full pool':>12}{'delta':>10}{'change':>10}")
    for name, m in cmp["metrics"].items():
        pct = "n/a" if m["pct_change"] is None else f"{m['pct_change']:+.1f}%"
        print(f"{name:<28}{m['assigned']:>13.3f}{m['full_pool']:>12.3f}"
              f"{m['delta']:>+10.3f}{pct:>10}")

    print("\nLaTeX table body for the results chapter")
    print("-" * 72)
    label = {
        "repetition_rate": "Statistic repetition rate",
        "repeated_statistics": "Repeated statistics (count)",
        "max_section_spread": "Worst-case section spread",
        "source_concentration": "Source concentration",
        "max_source_spread": "Worst-case source spread",
    }
    for name, m in cmp["metrics"].items():
        pct = "---" if m["pct_change"] is None else f"{m['pct_change']:+.1f}\\%"
        print(f"    {label.get(name, name)} & {m['full_pool']:.3f} & "
              f"{m['assigned']:.3f} & {pct} \\\\ \\hline")

    print("\nLower is better for every metric above.")
    print(f"n = {len(on)} treatment, {len(off)} control. Report these counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
