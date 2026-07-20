"""
Keyword Optimization Module
Analyzes and optimizes keyword usage in blog content.

✅ FIX: The optimizer now ACTIVELY rewrites underperforming sections to inject
low-density keywords, rather than just generating a text report that is thrown away.
The rewrite is surgical — only the paragraph(s) with the lowest keyword presence
are touched, and the rewrite is explicitly instructed not to change other content.
"""

import re
import os
import logging
from typing import Dict, List

logger = logging.getLogger("blog_pipeline")


# ============================================================================
# ANALYSIS HELPERS (unchanged)
# ============================================================================

def analyze_keyword_density(text: str, keywords: List[str]) -> Dict:
    """
    Analyze how well keywords are integrated in the content.
    
    Returns a dict with metrics for each keyword:
    - count: number of occurrences
    - density: percentage (industry standard: 1-2%)
    - in_title: present in first 200 chars
    - in_first_paragraph: present in first 500 chars
    - in_headings: present in any heading
    - status: optimal/low/high
    """
    
    text_lower = text.lower()
    word_count = len(text.split())
    
    results = {}
    for keyword in keywords:
        keyword_lower = keyword.lower()
        
        # Count occurrences
        count = text_lower.count(keyword_lower)
        
        # Calculate density (industry standard: 1-2%)
        density = (count / word_count * 100) if word_count > 0 else 0
        
        # Check strategic placement
        in_title = keyword_lower in text[:200].lower()
        in_first_para = keyword_lower in text[:500].lower()
        
        # Check if in headings (lines starting with #)
        in_headings = bool(re.search(
            rf'^##+ .*{re.escape(keyword_lower)}.*$', 
            text, 
            re.MULTILINE | re.IGNORECASE
        ))
        
        # Determine status
        if 1 <= density <= 2.5:
            status = "optimal"
        elif density < 1:
            status = "low"
        else:
            status = "high"
        
        results[keyword] = {
            "count": count,
            "density": round(density, 2),
            "in_title": in_title,
            "in_first_paragraph": in_first_para,
            "in_headings": in_headings,
            "status": status
        }
    
    return results


def generate_optimization_suggestions(analysis: Dict) -> List[str]:
    """Generate actionable suggestions based on keyword analysis."""
    
    suggestions = []
    
    for keyword, stats in analysis.items():
        # Density suggestions
        if stats["status"] == "low":
            suggestions.append(
                f"• '{keyword}' appears only {stats['count']} times ({stats['density']}%). "
                f"Consider adding 1-2 more natural mentions to reach 1-2% density."
            )
        elif stats["status"] == "high":
            suggestions.append(
                f"• '{keyword}' appears {stats['count']} times ({stats['density']}%). "
                f"This may trigger keyword stuffing penalties. Consider removing some instances."
            )
        
        # Placement suggestions
        if not stats["in_title"]:
            suggestions.append(
                f"• '{keyword}' is missing from the title/introduction. "
                f"Add it to the first paragraph for better SEO."
            )
        
        if not stats["in_headings"]:
            suggestions.append(
                f"• '{keyword}' is not used in any headings (H2/H3). "
                f"Consider incorporating it into at least one subheading."
            )
    
    return suggestions


# ============================================================================
# ✅ NEW: ACTIVE KEYWORD INJECTOR
# ============================================================================

def _inject_missing_keywords(blog_text: str, low_keywords: List[str]) -> str:
    """
    Uses an LLM to naturally weave missing keywords into the blog content.

    Only called when one or more keywords have 'low' density (<1%).
    The prompt is surgical: it identifies the most relevant existing paragraph
    for each keyword and rewrites only that paragraph to include the keyword
    naturally. All other content is preserved verbatim.

    Returns the updated blog text, or the original text if the LLM call fails.
    """
    if not low_keywords:
        return blog_text

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

        keywords_list = "\n".join(f"  - {kw}" for kw in low_keywords)

        system_prompt = """You are an SEO editor. Your task is to naturally integrate missing keywords 
into a blog post WITHOUT changing the meaning, tone, facts, or overall structure.

RULES:
1. For each missing keyword, find the most relevant existing paragraph and rewrite ONLY that 
   paragraph to include the keyword naturally (1-2 times max).
2. Do NOT add new sections, headings, bullet points, or paragraphs.
3. Do NOT change any other part of the blog.
4. The keyword must read naturally — do not force it awkwardly.
5. Return the COMPLETE blog post with your targeted edits applied.
6. Maintain the exact same Markdown formatting (##, **, [], etc.)."""

        human_message = (
            f"KEYWORDS TO INJECT (currently appearing too rarely):\n{keywords_list}\n\n"
            f"BLOG POST TO UPDATE:\n{blog_text}"
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message)
        ])

        updated = response.content.strip()

        # Safety check: make sure we got back a real blog (not an empty response)
        if len(updated) > len(blog_text) * 0.7:
            logger.info(f"   ✅ Keywords injected: {low_keywords}")
            return updated
        else:
            logger.warning("   ⚠️ Injection response too short — keeping original content.")
            return blog_text

    except Exception as e:
        logger.warning(f"   ⚠️ Keyword injection failed (non-fatal): {e}. Keeping original.")
        return blog_text


# ============================================================================
# MAIN NODE
# ============================================================================

def keyword_optimizer_node(state: dict) -> dict:
    """
    Analyzes and optimizes keyword usage in the final blog.
    
    ✅ FIX: This node now ACTIVELY rewrites the blog to inject low-density
    keywords rather than just generating a passive report. The injection step
    uses gpt-4o-mini with a surgical prompt to avoid changing unrelated content.

    Steps:
    1. Analyze keyword density and placement
    2. For keywords with 'low' status: inject them into the blog via LLM rewrite
    3. Re-analyze after injection to confirm improvement
    4. Generate a comprehensive report reflecting the final state
    """
    
    print("--- 🎯 OPTIMIZING KEYWORDS ---")
    
    final_text = state.get("final", "")
    target_keywords = state.get("target_keywords", [])
    
    # Skip if no keywords specified
    if not target_keywords:
        print("   ⏭️ No keywords specified, skipping optimization.")
        return {}
    
    if not final_text:
        print("   ⚠️ No content to analyze yet.")
        return {}
    
    # --- Step 1: Initial analysis ---
    analysis = analyze_keyword_density(final_text, target_keywords)
    low_keywords = [kw for kw, stats in analysis.items() if stats["status"] == "low"]

    # --- Step 2: Active injection for low-density keywords ---
    updated_text = final_text
    injected = False
    if low_keywords:
        print(f"   🔧 Injecting {len(low_keywords)} underperforming keyword(s): {low_keywords}")
        updated_text = _inject_missing_keywords(final_text, low_keywords)
        injected = updated_text != final_text

        if injected:
            # Re-analyze after injection so the report reflects the actual final state
            analysis = analyze_keyword_density(updated_text, target_keywords)
    
    # --- Step 3: Build report ---
    suggestions = generate_optimization_suggestions(analysis)
    
    report = "KEYWORD OPTIMIZATION REPORT\n"
    report += "=" * 60 + "\n\n"
    
    optimal_count = sum(1 for stats in analysis.values() if stats["status"] == "optimal")
    if injected:
        report += f"✅ Active keyword injection applied for: {', '.join(low_keywords)}\n\n"
    report += f"📊 SUMMARY: {optimal_count}/{len(target_keywords)} keywords are optimally integrated\n\n"
    
    for keyword, stats in analysis.items():
        status_emoji = "✅" if stats["status"] == "optimal" else "⚠️" if stats["status"] == "low" else "❌"
        
        report += f"{status_emoji} {keyword.upper()}\n"
        report += f"   Occurrences: {stats['count']}\n"
        report += f"   Density: {stats['density']}% (optimal: 1-2%)\n"
        report += f"   In Title/Intro: {'✓' if stats['in_title'] else '✗'}\n"
        report += f"   In First Paragraph: {'✓' if stats['in_first_paragraph'] else '✗'}\n"
        report += f"   In Headings: {'✓' if stats['in_headings'] else '✗'}\n"
        report += f"   Status: {stats['status'].upper()}\n\n"
    
    if suggestions:
        report += "💡 REMAINING SUGGESTIONS\n"
        report += "-" * 60 + "\n"
        report += "\n".join(suggestions)
        report += "\n"
    else:
        report += "✅ EXCELLENT! All keywords are optimally integrated.\n"
        report += "No further optimization needed.\n"
    
    print(f"   📊 Analyzed {len(target_keywords)} keywords")
    print(f"   ✅ {optimal_count} optimal, ⚠️ {len(target_keywords) - optimal_count} need attention")
    
    result = {
        "keyword_analysis": analysis,
        "keyword_report":   report,
    }

    # ✅ Only update state["final"] if the blog was actually changed
    if injected:
        result["final"] = updated_text

    return result


def get_keyword_summary(analysis: Dict) -> str:
    """Generate a one-line summary of keyword optimization status."""
    
    if not analysis:
        return "No keywords analyzed"
    
    optimal = sum(1 for stats in analysis.values() if stats["status"] == "optimal")
    total = len(analysis)
    
    if optimal == total:
        return f"✅ All {total} keywords optimally integrated"
    elif optimal == 0:
        return f"⚠️ 0/{total} keywords optimized - needs work"
    else:
        return f"⚠️ {optimal}/{total} keywords optimized"