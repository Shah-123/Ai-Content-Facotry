from datetime import date
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State, RouterDecision
from Graph.templates import ROUTER_SYSTEM
from .utils import logger, llm, _job, _emit

def router_node(state: State) -> dict:
    _emit(_job(state), "router", "started", "Analyzing topic and deciding research strategy...")
    logger.info("🚦 ROUTING ---")
    decider = llm.with_structured_output(RouterDecision)
    as_of = state.get("as_of", date.today().isoformat())
    
    decision = decider.invoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=f"Topic: {state['topic']}\nAs-of date: {as_of}"),
    ])

    source_mode = (state.get("source_mode") or "").lower()
    if source_mode == "closed_book":
        needs_research = False
        mode = "closed_book"
    elif source_mode in ("hybrid", "open_book", "auto_topic"):
        needs_research = True
        mode = decision.mode if decision.mode != "closed_book" else "hybrid"
    else:
        needs_research = decision.needs_research
        mode = decision.mode

    # Determine context window: open_book uses breaking window (7 days), hybrid/evergreen uses full index (3650 days)
    if mode == "open_book":
        recency_days = 7
    else:
        recency_days = 3650  # 10 years for historical, educational, and hybrid evidence search

    # The source_mode override above can force needs_research=True for a topic
    # the LLM judged closed-book — and a closed-book decision returns an EMPTY
    # queries list (the schema asks for queries only "if research is needed").
    # Without this, research_node runs zero searches, logs "No results found",
    # and the pipeline writes an ungrounded post while reporting "hybrid" mode.
    # Observed on every evergreen/historical topic, since source_mode defaults
    # to "hybrid" for all web jobs.
    queries = list(decision.queries or [])
    if needs_research and not queries:
        queries = [state["topic"]]
        logger.info(
            "Research forced on by source_mode but the router returned no "
            f"queries — falling back to the topic itself: {state['topic']!r}"
        )

    logger.info(f"Mode: {mode} | Research Needed: {needs_research} | Queries: {len(queries)} | Recency: {recency_days} days")
    _emit(_job(state), "router", "completed", f"Mode: {mode} | Research: {needs_research}", {"mode": mode, "needs_research": needs_research})
    
    return {
        "needs_research": needs_research,
        "mode": mode,
        "queries": queries,
        "recency_days": recency_days,
        "as_of": as_of
    }
