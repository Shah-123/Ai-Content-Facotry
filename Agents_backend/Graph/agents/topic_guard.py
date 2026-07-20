"""
topic_guard.py — Pre-flight safety / suitability check for user-submitted blog topics.

Runs BEFORE a job is created so unsafe or nonsensical topics never enter the
pipeline (no router, no research, no LLM token spend, no folder creation).

Usage:
    from Graph.agents.topic_guard import evaluate_topic
    verdict = evaluate_topic("i want to eat rocks")
    if not verdict.is_safe:
        # Reject with verdict.reason / verdict.category
        ...
"""

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.templates import TOPIC_GUARD_SYSTEM
from .utils import logger, llm


class TopicGuardVerdict(BaseModel):
    """Output schema for the pre-flight topic safety check."""
    is_safe: bool = Field(description="True if the topic is publishable.")
    category: str = Field(
        description="One of: self_harm | illegal | misinformation | hate | sexual_minors | nonsense | ok"
    )
    reason: str = Field(description="One short sentence shown to the user.")
    suggested_topic: str = Field(default="", description="Optional safer rewrite, or empty.")


import re

# Cheap deterministic short-circuits — catch obvious junk without an LLM call.
_TRIVIAL_BAD = {"", "test", "hi", "hello", "asdf", "asdfgh", "asdfghjk", "lol", "ok"}


def _trivial_reject(topic: str) -> TopicGuardVerdict | None:
    t = topic.strip().lower()
    if not t:
        return TopicGuardVerdict(
            is_safe=False, category="nonsense",
            reason="❌ Topic is empty. Please enter a blog topic.",
            suggested_topic="",
        )
    if len(t) < 3:
        return TopicGuardVerdict(
            is_safe=False, category="nonsense",
            reason="❌ Topic too short",
            suggested_topic="",
        )
    if len(t) > 200:
        return TopicGuardVerdict(
            is_safe=False, category="nonsense",
            reason="❌ Topic too long",
            suggested_topic="",
        )
    if not any(c.isalpha() for c in t):
        return TopicGuardVerdict(
            is_safe=False, category="nonsense",
            reason="❌ No words detected",
            suggested_topic="",
        )
    if re.search(r'(.)\1{4,}', t) or t in _TRIVIAL_BAD:
        return TopicGuardVerdict(
            is_safe=False, category="nonsense",
            reason="❌ Gibberish detected",
            suggested_topic="",
        )
    return None


def evaluate_topic(topic: str) -> TopicGuardVerdict:
    """
    Run the pre-flight safety/suitability check on a user-submitted topic.

    Fails CLOSED on LLM errors (defaults to is_safe=True) so a flaky API key
    or network blip doesn't lock users out — the downstream pipeline is the
    secondary safety net.
    """
    trivial = _trivial_reject(topic)
    if trivial is not None:
        logger.info(f"🛡️ TopicGuard (trivial): rejected '{topic[:60]}' — {trivial.reason}")
        return trivial

    try:
        guard = llm.with_structured_output(TopicGuardVerdict)
        verdict: TopicGuardVerdict = guard.invoke([
            SystemMessage(content=TOPIC_GUARD_SYSTEM),
            HumanMessage(content=f"Topic: {topic.strip()}"),
        ])
        if verdict.is_safe:
            logger.info(f"🛡️ TopicGuard: ALLOW '{topic[:60]}' (category={verdict.category})")
        else:
            logger.warning(
                f"🛡️ TopicGuard: REJECT '{topic[:60]}' — "
                f"category={verdict.category}, reason={verdict.reason}"
            )
        return verdict
    except Exception as exc:
        # Fail open — never block the user because of an LLM error.
        logger.exception(f"🛡️ TopicGuard failed for '{topic[:60]}': {exc}. Failing open.")
        return TopicGuardVerdict(
            is_safe=True, category="ok",
            reason="Topic guard unavailable; allowing topic.",
            suggested_topic="",
        )
