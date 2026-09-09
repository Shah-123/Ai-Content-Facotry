import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from event_bus import emit as event_emit
from usage import UsageCallback

# One shared callback records token usage for every completion, including
# calls made through .with_structured_output(). Attaching it here means no
# call site needs to know about accounting. See usage.py.
_usage_cb = UsageCallback()

logger = logging.getLogger("blog_pipeline")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if os.getenv("DEBUG") else logging.INFO)

def _emit(*args, **kwargs):
    return event_emit(*args, **kwargs)

def _job(state) -> str:
    """Extract job ID from state (works for both State dict and payload dict)."""
    return state.get("_job_id", "")

def _safe_slug(title: str) -> str:
    """Creates a filename-safe slug from a string."""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"

def truncate_for_eval(text: str, limit: int, label: str, job_id: str = "") -> tuple:
    """Clip `text` to `limit` characters and report whether anything was lost.

    Evaluators cap their input to bound cost, but they did so silently: a
    4,447-word article (39,025 characters) was audited on 77% of its text and
    graded by G-Eval on 64% of it, with nothing in the logs, the reports or the
    scores to say so. A score computed over two thirds of an article is not the
    same measurement as one computed over all of it, and a reader of those
    numbers had no way to know which they were looking at.

    This does not raise the limits — that would just move the cost. It makes the
    loss visible, so a truncated score can be reported as one.

    Returns (clipped_text, info) where info is suitable for storing alongside
    the scores:
        {"truncated": bool, "chars_evaluated": int,
         "chars_total": int, "coverage": float}
    """
    total = len(text or "")
    clipped = (text or "")[:limit]
    info = {
        "truncated": total > limit,
        "chars_evaluated": len(clipped),
        "chars_total": total,
        "coverage": round(len(clipped) / total, 4) if total else 1.0,
    }
    if info["truncated"]:
        logger.warning(
            f"⚠️ {label}: input truncated to {limit:,} of {total:,} characters "
            f"({info['coverage']:.0%} of the article). The resulting score does "
            f"NOT cover the whole text — report it as a partial measurement."
        )
        _emit(
            job_id, "system", "working",
            f"{label} evaluated {info['coverage']:.0%} of the article "
            f"({limit:,} of {total:,} characters).",
            info,
        )
    return clipped, info


def get_llm(state: dict = None, temperature: float = 0.0) -> ChatOpenAI:
    """Return a ChatOpenAI instance for the model selected in state, if available.

    Only OpenAI models are supported — this builds a ChatOpenAI client, so a
    non-OpenAI model id (e.g. 'claude-3-5-sonnet') would be sent to the OpenAI
    API and fail. Anything unrecognised falls back to the configured default
    rather than blowing up mid-generation.
    """
    model_name = _QUALITY_MODEL
    requested = state.get("selected_model") if isinstance(state, dict) else None
    if requested:
        if requested.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
            model_name = requested
        else:
            logger.warning(
                f"Ignoring unsupported model '{requested}' — get_llm only builds "
                f"OpenAI clients. Falling back to '{model_name}'."
            )
    return ChatOpenAI(model=model_name, temperature=temperature,
                      timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES,
                      callbacks=[_usage_cb])

_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "gpt-5-mini")
_QUALITY_MODEL = os.getenv("LLM_QUALITY_MODEL", "gpt-5-mini")

# The EVALUATION judge is configured separately from the production models.
#
# WHY: `llm_quality` drives five different things — the QA auditor, the revision
# agent, the podcast scripter, the get_llm() fallback, and (previously) the
# G-Eval judge. Repointing LLM_QUALITY_MODEL to get an independent judge would
# therefore also swap the QA auditor and the reviser, so any change in scores
# could not be attributed to the judge alone. That confound made the
# independent-judge experiment invalid.
#
# LLM_JUDGE_MODEL is read ONLY by Graph/agents/evaluation.py. It defaults to
# LLM_QUALITY_MODEL, so behaviour is unchanged unless it is explicitly set:
#
#     LLM_JUDGE_MODEL=gpt-4o RUN_GOLDEN_TESTS=1 pytest tests/golden -v -s
#
# Temperature is pinned to 0 (not 0.1) because a grader should be as
# reproducible as the API allows.
_JUDGE_MODEL = os.getenv("LLM_JUDGE_MODEL", _QUALITY_MODEL)

# ---------------------------------------------------------------------------
# REQUEST TIMEOUT
# ---------------------------------------------------------------------------
# Unset, langchain-openai inherits the OpenAI SDK's default 600-second read
# timeout and retries twice — so one wedged request could occupy a worker
# thread for THIRTY MINUTES with no log line and no way to tell it apart from
# a slow model. Pipeline runs execute in FastAPI's bounded thread pool, and
# jobs awaiting human approval already hold threads for up to 20 minutes, so a
# hung call compounds directly into API-wide starvation.
#
# 180s comfortably covers the slowest observed call (the QA audit reads 30k
# characters); with 2 retries the worst case is ~9 minutes instead of ~30.
# Raise LLM_REQUEST_TIMEOUT if a larger model legitimately needs longer.
_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "180"))
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ---------------------------------------------------------------------------
# A NOTE ON temperature
# ---------------------------------------------------------------------------
# The temperature arguments below are NOT honoured by the default model.
# Reasoning-family models (the gpt-5 line) accept only their default sampling
# temperature, and langchain-openai drops the parameter silently rather than
# raising — the constructed client reports `temperature is None`:
#
#     ChatOpenAI(model="gpt-5-mini",  temperature=0.7).temperature  -> None
#     ChatOpenAI(model="gpt-4o-mini", temperature=0.7).temperature  -> 0.7
#
# The values are kept because they DO take effect when a caller selects a
# non-reasoning model through the UI's model selector (`selected_model`), and
# because they document the intent of each role. But nothing that depends on
# temperature actually varies on the default model — notably `llm_planner`
# below, whose 0.7 was chosen to diversify outlines. If outline variety turns
# out to matter, vary the prompt, not this number.
# tests/test_evaluation.py::TestTemperatureIsInertOnReasoningModels guards this
# so the finding is not silently rediscovered.
llm_fast = ChatOpenAI(model=_FAST_MODEL, temperature=0,
                      timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES,
                      callbacks=[_usage_cb])
llm_quality = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.1,
                         timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES,
                      callbacks=[_usage_cb])
llm_judge = ChatOpenAI(model=_JUDGE_MODEL, temperature=0,
                       timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES,
                      callbacks=[_usage_cb])
# Planner LLM uses higher temperature so blog outlines vary across runs
# instead of converging on the same headings for the same topic.
llm_planner = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.7,
                         timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES,
                      callbacks=[_usage_cb])

# Backward compat alias
llm = llm_fast
