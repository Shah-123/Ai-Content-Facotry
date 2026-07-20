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

    # Determine context window
    if decision.mode == "open_book":
        recency_days = 7
    elif decision.mode == "hybrid":
        recency_days = 45
    else:
        recency_days = 3650 # 10 years

    logger.info(f"Mode: {decision.mode} | Research Needed: {decision.needs_research}")
    _emit(_job(state), "router", "completed", f"Mode: {decision.mode} | Research: {decision.needs_research}", {"mode": decision.mode, "needs_research": decision.needs_research})
    
    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries,
        "recency_days": recency_days,
        "as_of": as_of
    }
