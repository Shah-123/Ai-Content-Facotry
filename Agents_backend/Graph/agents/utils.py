import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from event_bus import emit as event_emit

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
    return ChatOpenAI(model=model_name, temperature=temperature)

_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "gpt-5-mini")
_QUALITY_MODEL = os.getenv("LLM_QUALITY_MODEL", "gpt-5-mini")

llm_fast = ChatOpenAI(model=_FAST_MODEL, temperature=0)
llm_quality = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.1)
# Planner LLM uses higher temperature so blog outlines vary across runs
# instead of converging on the same headings for the same topic.
llm_planner = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.7)

# Backward compat alias
llm = llm_fast
