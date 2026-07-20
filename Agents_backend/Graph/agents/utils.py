import os
import re
import logging
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

_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "gpt-4o-mini")
_QUALITY_MODEL = os.getenv("LLM_QUALITY_MODEL", "gpt-4o-mini")

llm_fast = ChatOpenAI(model=_FAST_MODEL, temperature=0)
llm_quality = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.1)
# Planner LLM uses higher temperature so blog outlines vary across runs
# instead of converging on the same headings for the same topic.
llm_planner = ChatOpenAI(model=_QUALITY_MODEL, temperature=0.7)

# Backward compat alias
llm = llm_fast
