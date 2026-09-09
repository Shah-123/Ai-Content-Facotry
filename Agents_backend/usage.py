"""
usage.py — Token and cost accounting for LLM calls.

WHY THIS EXISTS
---------------
The project had no instrumentation of any kind: no token counts, no timing, no
cost. That made several claims unverifiable and they had to be removed from the
thesis rather than defended. This module supplies the measurement so a figure
can be reported with the data behind it.

HOW IT WORKS
------------
`UsageCallback` is a LangChain callback attached to every model client in
Graph/agents/utils.py. LangChain fires `on_llm_end` for every completion —
including calls made through `.with_structured_output(...)`, which is how most
of this codebase invokes models — so no call site needs to change.

Counts accumulate into one process-wide, lock-protected total. A run is measured
by taking a `snapshot()` before it starts and calling `delta()` afterwards:

    before = usage.snapshot()
    ...run the pipeline...
    report = usage.delta(before)

That approach is deliberate. LangGraph dispatches section writers to worker
threads via `Send`, and contextvar-based accounting (`get_openai_callback`) does
not follow execution into threads it did not create, so parallel writers would
be silently omitted — precisely the calls that dominate a run. A global counter
plus a snapshot has no such blind spot. It assumes one pipeline at a time per
process, which is the documented single-worker deployment; concurrent runs would
share a total, and `delta()` would over-report.

Prices are estimates, are stated per model, and are overridable. Any figure
derived from them must be reported as an estimate with its price basis.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
# USD per 1,000,000 tokens, as (input, output). Published list prices, recorded
# 2026-09. Vendors change these, so treat any derived cost as an estimate and
# state the basis. Override a model with, e.g.:
#     LLM_PRICE_GPT_5_MINI="0.25,2.00"
_DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}

_UNKNOWN_MODEL_PRICE = (0.0, 0.0)


def _price_for(model: str) -> tuple[float, float]:
    """Per-million (input, output) price for a model, honouring env overrides."""
    env_key = "LLM_PRICE_" + model.upper().replace("-", "_").replace(".", "_")
    raw = os.getenv(env_key, "").strip()
    if raw:
        try:
            inp, out = (float(p) for p in raw.split(",", 1))
            return inp, out
        except ValueError:
            pass
    # Longest-prefix match so dated snapshots (gpt-4o-2024-11-20) still price.
    for known in sorted(_DEFAULT_PRICES, key=len, reverse=True):
        if model.startswith(known):
            return _DEFAULT_PRICES[known]
    return _UNKNOWN_MODEL_PRICE


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_totals: dict[str, dict[str, int]] = defaultdict(
    lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0}
)


def record(model: str, input_tokens: int, output_tokens: int) -> None:
    """Add one call's usage to the process-wide total. Thread-safe."""
    with _lock:
        row = _totals[model or "unknown"]
        row["calls"] += 1
        row["input_tokens"] += int(input_tokens or 0)
        row["output_tokens"] += int(output_tokens or 0)


def snapshot() -> dict[str, dict[str, int]]:
    """Deep copy of the current totals, for use as a `delta()` baseline."""
    with _lock:
        return {m: dict(v) for m, v in _totals.items()}


def reset() -> None:
    """Clear all counters. Intended for tests."""
    with _lock:
        _totals.clear()


def delta(before: dict[str, dict[str, int]] | None = None) -> dict[str, Any]:
    """Usage accrued since `before` (or since process start if omitted).

    Returns per-model rows plus a total, with estimated cost in USD:

        {
          "by_model": {"gpt-5-mini": {calls, input_tokens, output_tokens,
                                      cost_usd, price_per_1m_input, ...}},
          "total": {calls, input_tokens, output_tokens, total_tokens, cost_usd},
          "priced": bool,     # False if any model had no known price
        }
    """
    before = before or {}
    now = snapshot()

    by_model: dict[str, dict[str, Any]] = {}
    tot_calls = tot_in = tot_out = 0
    tot_cost = 0.0
    priced = True

    for model, row in now.items():
        base = before.get(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        calls = row["calls"] - base["calls"]
        inp = row["input_tokens"] - base["input_tokens"]
        out = row["output_tokens"] - base["output_tokens"]
        if calls <= 0 and inp <= 0 and out <= 0:
            continue

        p_in, p_out = _price_for(model)
        if (p_in, p_out) == _UNKNOWN_MODEL_PRICE:
            priced = False
        cost = (inp / 1_000_000) * p_in + (out / 1_000_000) * p_out

        by_model[model] = {
            "calls": calls,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
            "cost_usd": round(cost, 6),
            "price_per_1m_input": p_in,
            "price_per_1m_output": p_out,
        }
        tot_calls += calls
        tot_in += inp
        tot_out += out
        tot_cost += cost

    return {
        "by_model": by_model,
        "total": {
            "calls": tot_calls,
            "input_tokens": tot_in,
            "output_tokens": tot_out,
            "total_tokens": tot_in + tot_out,
            "cost_usd": round(tot_cost, 6),
        },
        "priced": priced,
    }


def format_report(usage: dict[str, Any]) -> str:
    """Human-readable report for reports/token_usage.txt."""
    lines = [
        "TOKEN USAGE AND ESTIMATED COST",
        "=" * 60,
    ]
    t = usage["total"]
    lines += [
        f"LLM calls:      {t['calls']}",
        f"Input tokens:   {t['input_tokens']:,}",
        f"Output tokens:  {t['output_tokens']:,}",
        f"Total tokens:   {t['total_tokens']:,}",
        f"Estimated cost: ${t['cost_usd']:.4f} USD",
        "",
        "Per model",
        "-" * 60,
    ]
    for model, row in sorted(
        usage["by_model"].items(), key=lambda kv: -kv[1]["cost_usd"]
    ):
        lines += [
            f"{model}",
            f"    calls {row['calls']:>4}   "
            f"in {row['input_tokens']:>8,}   out {row['output_tokens']:>7,}   "
            f"${row['cost_usd']:.4f}",
            f"    priced at ${row['price_per_1m_input']}/1M in, "
            f"${row['price_per_1m_output']}/1M out",
        ]
    if not usage["priced"]:
        lines += [
            "",
            "NOTE: at least one model has no known price; the total is a LOWER BOUND.",
        ]
    lines += [
        "",
        "Cost is an ESTIMATE from published list prices at the date recorded in",
        "usage.py. Report it as an estimate and state the price basis.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# LangChain callback
# ---------------------------------------------------------------------------


class UsageCallback(BaseCallbackHandler):
    """Records token usage for every completion, including structured output.

    Attached once per client in Graph/agents/utils.py, so call sites are
    unchanged. Must never raise: an accounting failure must not break a
    generation run.
    """

    raise_error = False

    def on_llm_end(self, response, **kwargs: Any) -> None:  # noqa: ANN001
        try:
            model = ""
            if getattr(response, "llm_output", None):
                model = response.llm_output.get("model_name") or ""

            for generation_list in getattr(response, "generations", []) or []:
                for generation in generation_list or []:
                    message = getattr(generation, "message", None)
                    usage = getattr(message, "usage_metadata", None) if message else None
                    if usage:
                        if not model:
                            meta = getattr(message, "response_metadata", {}) or {}
                            model = meta.get("model_name") or meta.get("model") or ""
                        record(
                            model or "unknown",
                            usage.get("input_tokens", 0),
                            usage.get("output_tokens", 0),
                        )
        except Exception:  # noqa: BLE001 - accounting must never break a run
            pass


def demo() -> None:
    """Self-check: no network, no API key."""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    reset()
    cb = UsageCallback()

    def _result(model: str, inp: int, out: int) -> LLMResult:
        msg = AIMessage(
            content="x",
            usage_metadata={"input_tokens": inp, "output_tokens": out,
                            "total_tokens": inp + out},
        )
        return LLMResult(
            generations=[[ChatGeneration(message=msg)]],
            llm_output={"model_name": model},
        )

    base = snapshot()
    cb.on_llm_end(_result("gpt-5-mini", 1000, 500))
    cb.on_llm_end(_result("gpt-5-mini", 2000, 800))
    cb.on_llm_end(_result("gpt-4o", 500, 100))

    d = delta(base)
    assert d["total"]["calls"] == 3, d
    assert d["total"]["input_tokens"] == 3500, d
    assert d["total"]["output_tokens"] == 1400, d
    assert d["by_model"]["gpt-5-mini"]["calls"] == 2

    # 3000/1M * 0.25 + 1300/1M * 2.00 = 0.00075 + 0.0026 = 0.00335
    assert abs(d["by_model"]["gpt-5-mini"]["cost_usd"] - 0.00335) < 1e-6, d
    assert d["priced"] is True

    # delta() is relative to the baseline, not cumulative
    mid = snapshot()
    cb.on_llm_end(_result("gpt-5-mini", 100, 100))
    assert delta(mid)["total"]["calls"] == 1

    # unknown models are counted but flagged as unpriced
    cb.on_llm_end(_result("some-future-model", 10, 10))
    assert delta(base)["priced"] is False

    # dated snapshots still price via longest-prefix match
    assert _price_for("gpt-4o-2024-11-20") == _DEFAULT_PRICES["gpt-4o"]

    # a malformed response must not raise
    cb.on_llm_end(object())

    reset()
    print(format_report(d))
    print("all self-checks passed")


if __name__ == "__main__":
    demo()
