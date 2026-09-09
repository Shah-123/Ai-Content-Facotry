"""
metrics.py — Repetition and source-spread measurement for generated articles.

WHY THIS EXISTS
---------------
`_assign_evidence_to_tasks()` in orchestrator.py was written to fix an observed
defect: with 9 sections and only 5 evidence items, every parallel worker saw the
whole evidence pool and independently gravitated to the same two or three most
prominent statistics. A single post repeated "70% of organisations use AI" and
"GI Genius reduces missed polyps by 50%" seven or more times.

The fix partitions evidence so each worker sees only its own slice. Until now
there was no measurement of whether that actually worked. These functions supply
the dependent variables for the ablation:

    arm A (assign_evidence=True)  -> workers receive disjoint evidence slices
    arm B (assign_evidence=False) -> workers receive the full pool (pre-fix)

Primary metric   : repeated_statistics()  — directly measures the reported defect
Secondary metric : source_spread()        — measures citation concentration

Both are deterministic text analyses. No model is involved in scoring, so the
numbers cannot be disputed as judge bias.

Run the built-in self-check with:
    python -m tests.golden.metrics
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

# A "statistic" is a number that carries meaning a writer would repeat: a
# percentage, a currency amount, a scaled figure (3.5 billion), or a multiplier.
# Bare small integers are excluded — "3 steps" is not a statistic being reused,
# and counting it would swamp the signal with noise.
_STAT_PATTERNS = [
    r"\d[\d,]*\.?\d*\s*%",                                   # 70%, 12.5 %
    r"[$£€]\s?\d[\d,]*\.?\d*\s*(?:billion|million|trillion|bn|m|k)?",  # $1.25 trillion
    r"\d[\d,]*\.?\d*\s*(?:billion|million|trillion)",         # 3.5 billion
    r"\d[\d,]*\.?\d*\s*x\b",                                  # 10x
]
_STAT_RE = re.compile("|".join(f"(?:{p})" for p in _STAT_PATTERNS), re.IGNORECASE)

_H2_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)
_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")
# Everything after this heading is the auto-generated references table, not prose.
_REFERENCES_HEADING = "### 📚 References & Cited Sources"


def _strip_references(markdown: str) -> str:
    """Drop the generated references table and SEO block.

    Both list every source once by construction, so leaving them in would count
    a citation in the bibliography as if it were a repetition in the body.
    """
    idx = markdown.find(_REFERENCES_HEADING)
    return markdown[:idx] if idx != -1 else markdown


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split an article into (heading, body) pairs on H2 boundaries.

    Content before the first H2 (the H1 title, any hero image) is ignored: it is
    not a section a worker wrote.
    """
    body = _strip_references(markdown)
    matches = list(_H2_RE.finditer(body))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((m.group(1).strip(), body[start:end]))
    return out


def normalise_stat(raw: str) -> str:
    """Canonicalise a statistic so '70 %' and '70%' compare equal."""
    s = raw.lower().replace(",", "").replace(" ", "")
    s = s.replace("bn", "billion").replace("$", "$")
    return s


def extract_statistics(text: str) -> set[str]:
    """Distinct normalised statistics appearing in a span of text."""
    return {normalise_stat(m.group(0)) for m in _STAT_RE.finditer(text)}


def repeated_statistics(markdown: str) -> dict:
    """PRIMARY METRIC. How often does the same statistic resurface elsewhere?

    Returns:
        {
          "sections": int,
          "distinct_statistics": int,
          "repeated_statistics": int,     # appear in >1 section
          "max_section_spread": int,      # worst offender's section count
          "repetition_rate": float,       # repeated / distinct  (0.0 = ideal)
          "detail": {stat: section_count} # only those appearing in >1 section
        }

    Lower repetition_rate is better. A statistic legitimately introduced once and
    referenced once more scores 2; the defect this measures looked like 7.
    """
    sections = split_sections(markdown)
    per_section = [extract_statistics(body) for _, body in sections]

    counts: Counter = Counter()
    for stats in per_section:
        counts.update(stats)  # set per section => counts sections, not mentions

    repeated = {s: c for s, c in counts.items() if c > 1}
    distinct = len(counts)
    return {
        "sections": len(sections),
        "distinct_statistics": distinct,
        "repeated_statistics": len(repeated),
        "max_section_spread": max(counts.values()) if counts else 0,
        "repetition_rate": round(len(repeated) / distinct, 4) if distinct else 0.0,
        "detail": dict(sorted(repeated.items(), key=lambda kv: -kv[1])),
    }


def source_spread(markdown: str) -> dict:
    """SECONDARY METRIC. Are citations spread across sources, or concentrated?

    Returns:
        {
          "sections": int,
          "distinct_sources": int,
          "sources_cited_in_multiple_sections": int,
          "max_source_spread": int,
          "mean_sources_per_section": float,
          "concentration": float   # reused / distinct (0.0 = perfectly disjoint)
        }
    """
    sections = split_sections(markdown)
    per_section = [{m.group(1) for m in _LINK_RE.finditer(body)} for _, body in sections]

    counts: Counter = Counter()
    for urls in per_section:
        counts.update(urls)

    reused = [u for u, c in counts.items() if c > 1]
    distinct = len(counts)
    total_citations = sum(len(u) for u in per_section)
    return {
        "sections": len(sections),
        "distinct_sources": distinct,
        "sources_cited_in_multiple_sections": len(reused),
        "max_source_spread": max(counts.values()) if counts else 0,
        "mean_sources_per_section": round(total_citations / len(sections), 2) if sections else 0.0,
        "concentration": round(len(reused) / distinct, 4) if distinct else 0.0,
    }


def article_metrics(markdown: str) -> dict:
    """Both metrics, as stored in a golden run's summary.json."""
    return {
        "repetition": repeated_statistics(markdown),
        "sources": source_spread(markdown),
    }


def compare_arms(arm_on: Iterable[dict], arm_off: Iterable[dict]) -> dict:
    """Aggregate the two ablation arms into a reportable comparison.

    Each argument is an iterable of `article_metrics()` dicts (one per run).
    Returns means per arm plus the absolute and relative change, so the result
    can be pasted straight into a results table.
    """
    def _mean(rows: list[dict], *path: str) -> float:
        vals = []
        for r in rows:
            cur = r
            for k in path:
                cur = cur[k]
            vals.append(cur)
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    on, off = list(arm_on), list(arm_off)
    out: dict = {"n_assigned": len(on), "n_full_pool": len(off), "metrics": {}}
    for label, path in [
        ("repetition_rate", ("repetition", "repetition_rate")),
        ("repeated_statistics", ("repetition", "repeated_statistics")),
        ("max_section_spread", ("repetition", "max_section_spread")),
        ("source_concentration", ("sources", "concentration")),
        ("max_source_spread", ("sources", "max_source_spread")),
    ]:
        a, b = _mean(on, *path), _mean(off, *path)
        out["metrics"][label] = {
            "assigned": a,
            "full_pool": b,
            "delta": round(a - b, 4),
            "pct_change": round((a - b) / b * 100, 1) if b else None,
        }
    return out


# ---------------------------------------------------------------------------
# Self-check — runnable without pytest, no network, no API keys.
# ---------------------------------------------------------------------------

def demo() -> None:
    repetitive = """# Title

## Introduction
Adoption is rising: 70% of organisations now use AI, a $3.5 billion market.

## Current Landscape
As noted, 70% of organisations now use AI. Spending reached $3.5 billion.

## Outlook
Again, 70% of organisations use AI and the $3.5 billion figure keeps growing.
"""
    distributed = """# Title

## Introduction
Adoption is rising: 70% of organisations now use AI.

## Current Landscape
Spending reached $3.5 billion across the sector.

## Outlook
Deployment velocity improved 10x year over year.
"""

    bad = repeated_statistics(repetitive)
    good = repeated_statistics(distributed)

    assert bad["sections"] == 3, bad
    assert good["sections"] == 3, good
    # Both stats recur in all three sections of the repetitive article.
    assert bad["max_section_spread"] == 3, bad
    assert bad["repeated_statistics"] == 2, bad
    assert bad["repetition_rate"] == 1.0, bad
    # The distributed article reuses nothing.
    assert good["repeated_statistics"] == 0, good
    assert good["repetition_rate"] == 0.0, good
    assert good["max_section_spread"] == 1, good

    # Normalisation: spacing and thousands separators must not create duplicates.
    assert extract_statistics("70% and 70 %") == {"70%"}
    assert extract_statistics("1,250 million") == {"1250million"}

    # The references table must not count as body repetition.
    with_refs = distributed + "\n\n### 📚 References & Cited Sources\n\n| 70% | 70% |\n"
    assert repeated_statistics(with_refs)["repeated_statistics"] == 0

    # Source spread on a disjoint vs shared citation pattern.
    shared = """## A
[x](https://a.com) [y](https://b.com)

## B
[x](https://a.com) [y](https://b.com)
"""
    disjoint = """## A
[x](https://a.com)

## B
[y](https://b.com)
"""
    assert source_spread(shared)["concentration"] == 1.0
    assert source_spread(disjoint)["concentration"] == 0.0

    # compare_arms consumes article_metrics() shapes, not bare metric dicts.
    cmp = compare_arms([article_metrics(distributed)], [article_metrics(repetitive)])
    assert cmp["metrics"]["repetition_rate"]["delta"] == -1.0, cmp
    assert cmp["metrics"]["repetition_rate"]["pct_change"] == -100.0, cmp
    assert cmp["n_assigned"] == 1 and cmp["n_full_pool"] == 1

    print("repetitive article :", {k: v for k, v in bad.items() if k != "detail"})
    print("distributed article:", {k: v for k, v in good.items() if k != "detail"})
    print("comparison         :", cmp["metrics"]["repetition_rate"])
    print("\nall self-checks passed")


if __name__ == "__main__":
    demo()
