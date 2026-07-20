import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.tools.tavily_search import TavilySearchResults

from Graph.state import State, EvidencePack
from Graph.templates import RESEARCH_SYSTEM
from .utils import logger, llm, _job, _emit

# ✅ FIX: Similarity threshold for near-duplicate detection.
# Two snippets are considered duplicates if they share this proportion
# of words. 0.65 catches syndicated articles (same content, different URLs)
# without being so aggressive it drops genuinely related sources.
_DUPLICATE_SIMILARITY_THRESHOLD = 0.65

# ✅ FIX: Fallback recency window used when the router did not set recency_days.
# Matches the closed_book default in routing.py (10 years).
_DEFAULT_RECENCY_DAYS = 3650


def _snippet_fingerprint(snippet: str) -> set:
    """
    Converts a snippet into a set of meaningful words for overlap comparison.
    Strips short stop-words (len <= 3) to focus on content words only.
    """
    words = snippet.lower().split()
    return {w for w in words if len(w) > 3}


def _is_near_duplicate(snippet: str, seen_fingerprints: List[set]) -> bool:
    """
    Returns True if the snippet is too similar to any already-accepted result.
    Uses Jaccard similarity: overlap / union of word sets.

    Example: two syndicated versions of the same article will share ~80%
    of their content words → flagged as duplicate, skipped.
    """
    candidate = _snippet_fingerprint(snippet)
    if not candidate:
        return False

    for seen in seen_fingerprints:
        if not seen:
            continue
        overlap = len(candidate & seen)
        union   = len(candidate | seen)
        if union > 0 and (overlap / union) >= _DUPLICATE_SIMILARITY_THRESHOLD:
            return True

    return False


def _tavily_search(query: str, max_results: int = 5, recency_days: int = _DEFAULT_RECENCY_DAYS) -> List[dict]:
    """
    Safe Tavily search wrapper.

    ✅ FIX: recency_days is now accepted as a parameter and forwarded to
    Tavily's `days` argument. Previously this was hardcoded to no filter,
    meaning open_book topics (e.g. "AI trends 2026") could return articles
    from years ago while routing.py had already correctly computed that only
    the last 7 days were relevant. The value flows:

        routing.py  →  state["recency_days"]  →  research_node  →  here
    """
    if not os.getenv("TAVILY_API_KEY"):
        logger.warning("TAVILY_API_KEY missing. Skipping search.")
        return []
    try:
        tool = TavilySearchResults(max_results=max_results, days=recency_days)
        results = tool.invoke({"query": query})
        out: List[dict] = []
        for r in results or []:
            out.append({
                "title":        r.get("title", ""),
                "url":          r.get("url", ""),
                "snippet":      r.get("content") or r.get("snippet", ""),
                "published_at": r.get("published_date") or r.get("published_at"),
                "source":       r.get("source"),
            })
        return out
    except Exception as e:
        logger.warning(f"Search failed for '{query}': {e}")
        return []


def scrape_full_webpage_fallback(url: str, max_words: int = 1500) -> str:
    """Fallback: visits a URL and scrapes the actual article text using BeautifulSoup."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, 'html.parser')

        for script in soup(["script", "style", "nav", "footer", "aside"]):
            script.decompose()

        text = soup.get_text(separator=' ', strip=True)
        words = text.split()
        return " ".join(words[:max_words])

    except Exception as e:
        logger.warning(f"Fallback scrape failed for {url}: {e}")
        return ""


def scrape_full_webpage(url: str, max_words: int = 1500) -> str:
    """Primary: Converts URL to clean Markdown using Jina Reader API for optimal LLM ingestion."""
    try:
        if not url.startswith("http"):
            return ""

        jina_url = f"https://r.jina.ai/{url}"
        headers = {'Accept': 'text/event-stream'}

        logger.info(f"Using Jina Reader for: {url}")
        # ✅ FIX: Reduced timeout from 15s → 8s. Most successful Jina responses
        # arrive in under 5s. The old 15s timeout just meant waiting longer for
        # pages that would ultimately fail (4/10 timed out in the user's run).
        response = requests.get(jina_url, headers=headers, timeout=8)

        if response.status_code == 200:
            text = response.text
            words = text.split()
            if len(words) < 50:
                logger.warning(f"Jina returned very little content for {url}. Attempting fallback.")
                return scrape_full_webpage_fallback(url, max_words)
            return " ".join(words[:max_words])

        else:
            logger.warning(f"Jina Reader failed ({response.status_code}) for {url}. Attempting fallback.")
            return scrape_full_webpage_fallback(url, max_words)

    except Exception as e:
        logger.warning(f"Jina Reader exception on {url}: {e}. Attempting fallback.")
        return scrape_full_webpage_fallback(url, max_words)


def research_node(state: State) -> dict:
    _emit(_job(state), "research", "started", "Searching the web for evidence...")
    logger.info("🔍 DEEP RESEARCHING ---")

    queries = (state.get("queries") or [])[:5]

    # ✅ FIX: Read recency_days from state so the date window router.py computed
    # actually affects which results Tavily returns.
    # - open_book  →  7 days   (breaking news, current events)
    # - hybrid     →  45 days  (recent but not breaking)
    # - closed_book → 3650 days (effectively no date filter)
    recency_days = state.get("recency_days", _DEFAULT_RECENCY_DAYS)
    logger.info(f"📅 Search recency window: {recency_days} days")

    found_urls = set()
    seen_fingerprints: List[set] = []
    raw_results = []
    duplicates_skipped = 0

    # ✅ FIX: Parallelize Tavily searches.
    # Previously 5 queries ran one-by-one (~4s each = ~20s total).
    # Now they run concurrently in ~5s.
    logger.info(f"🔎 Running {len(queries)} search queries in parallel...")
    _emit(_job(state), "research", "working", f"Searching {len(queries)} queries in parallel...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_query = {
            executor.submit(_tavily_search, q, 5, recency_days): q
            for q in queries
        }
        for future in as_completed(future_to_query):
            q = future_to_query[future]
            logger.info(f"Searching: {q}")
            try:
                results = future.result()
            except Exception as e:
                logger.warning(f"Search failed for '{q}': {e}")
                continue

            for r in results:
                # Gate 1: exact URL deduplication (unchanged)
                if r['url'] in found_urls:
                    continue

                # Gate 2: near-duplicate snippet detection
                snippet = r.get("snippet", "")
                if _is_near_duplicate(snippet, seen_fingerprints):
                    logger.info(f"   ⏭️ Skipping near-duplicate: {r['url']}")
                    duplicates_skipped += 1
                    continue

                # Accept this result
                found_urls.add(r['url'])
                seen_fingerprints.append(_snippet_fingerprint(snippet))
                raw_results.append(r)

    if duplicates_skipped:
        logger.info(f"   🧹 Skipped {duplicates_skipped} near-duplicate result(s)")

    # ✅ Document upload support: preserve any evidence already loaded by
    # `document_ingest_node` running before us in the graph. We merge the
    # web-research evidence on top instead of overwriting state["evidence"].
    pre_existing = list(state.get("evidence") or [])

    if not raw_results:
        logger.warning("No results found.")
        _emit(_job(state), "research", "completed", "No results found", {"sources": 0})
        return {"evidence": pre_existing}

    # ✅ FIX: Parallelize web scraping.
    # Previously 10 URLs scraped one-by-one with 15s timeout each = ~120s.
    # Now they scrape concurrently in ~15-20s total.
    top_results = raw_results[:15]
    logger.info(f"🕸️ Scraping {len(top_results)} top articles in parallel...")
    _emit(_job(state), "research", "working", f"Deep-scraping {len(top_results)} articles in parallel...")

    deep_evidence_context = ""
    scraped_parts = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {
            executor.submit(scrape_full_webpage, r['url']): (idx, r)
            for idx, r in enumerate(top_results)
        }
        for future in as_completed(future_to_item):
            idx, r = future_to_item[future]
            logger.info(f"-> Reading: {r['url']}")
            try:
                full_text = future.result()
                if full_text:
                    scraped_parts[idx] = (r, full_text)
            except Exception as e:
                logger.warning(f"Scrape failed for {r['url']}: {e}")

    # Reassemble in original order for deterministic evidence extraction
    for idx in sorted(scraped_parts.keys()):
        r, full_text = scraped_parts[idx]
        deep_evidence_context += f"SOURCE {idx+1}: {r['title']} ({r['url']})\n"
        deep_evidence_context += f"CONTENT: {full_text[:3000]}\n\n"

    logger.info("🧠 Analyzing full articles for hard evidence...")
    _emit(_job(state), "research", "working", "Extracting verified facts from articles...")

    extractor = llm.with_structured_output(EvidencePack)
    pack = extractor.invoke([
        SystemMessage(content=RESEARCH_SYSTEM),
        HumanMessage(content=(
            f"Topic: {state['topic']}\n"
            f"Read the following full articles and extract 8–10 UNIQUE hard facts, statistics, and verifiable claims.\n"
            f"Ensure evidence comes from DIVERSE sources — do not extract multiple items from the same article unless they contain genuinely distinct facts.\n\n"
            f"SCRAPED ARTICLES:\n{deep_evidence_context}"
        )),
    ])

    web_evidence = list({e.url: e for e in pack.evidence if e.url}.values())

    # ✅ Merge with any document-derived evidence preserved at the start of
    # this node so hybrid mode (upload + web) keeps both sources for citation.
    merged: list = list(pre_existing)
    seen_keys = {(getattr(e, "url", None), getattr(e, "snippet", None)[:80] if getattr(e, "snippet", None) else None) for e in pre_existing}
    for ev in web_evidence:
        key = (ev.url, (ev.snippet or "")[:80])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(ev)

    logger.info(
        f"✅ Extracted {len(web_evidence)} web evidence items "
        f"(+ {len(pre_existing)} pre-existing from upload)."
    )
    _emit(_job(state), "research", "completed",
          f"Found {len(web_evidence)} web sources (total evidence: {len(merged)})",
          {"sources": len(web_evidence), "total": len(merged)})
    return {"evidence": merged}