import os
import re
from typing import Tuple, Dict, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
class BlogEvaluator:
    """
    Quality evaluator that uses LLM-as-a-Judge to comprehensively grade
    the finished blog post across four dimensions.
    """

    def __init__(self, model_name: str = "gpt-5-mini"):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger_warning = "OPENAI_API_KEY not found in environment for BlogEvaluator"
            print(f"⚠️ {logger_warning}")
            self.llm = None
        else:
            self.llm = ChatOpenAI(model=model_name, temperature=0, api_key=api_key)

    def evaluate(self, blog_post: str, topic: str) -> Dict[str, Any]:
        """Run complete AI evaluation. Returns a structured result dict."""
        from typing import List
        from pydantic import BaseModel, Field

        if not self.llm:
            return {
                "final_score": 0.0,
                "verdict": "❌ MISSING_API_KEY",
                "metrics": {},
                "raw_counts": {
                    "word_count": len(blog_post.split()),
                    "link_count": len(re.findall(r'\[.*?\]\(https?://', blog_post)),
                    "unique_domains": len(set(re.findall(r'https?://(?:www\.)?([^/]+)', blog_post))),
                },
                "ai_feedback": {"error": "OPENAI_API_KEY missing", "strengths": [], "improvements": []},
            }

        class BlogFeedback(BaseModel):
            depth_score: float = Field(
                description="Score 0-10 on how comprehensively and accurately the topic is covered. Penalize fluff or hallucinations."
            )
            structure_score: float = Field(
                description="Score 0-10 on logical flow, use of headers (H1, H2, H3), bullet points, and paragraph sizing."
            )
            readability_score: float = Field(
                description="Score 0-10 on human-like tone, sentence variety, and avoidance of AI cliches (e.g. 'In conclusion')."
            )
            seo_and_links_score: float = Field(
                description="Score 0-10 on the presence of inline citations [Source](url) and keyword inclusion."
            )
            strengths: List[str] = Field(description="3 specific strengths of this article.")
            improvements: List[str] = Field(description="2 actionable improvements.")
            overall_impression: str = Field(description="Brief overall impression.")

        evaluator = self.llm.with_structured_output(BlogFeedback).with_retry(
            stop_after_attempt=3
        )

        system_message = """You are an elite blog editor and content quality rater.
Your job is to read the provided blog post (in Markdown) and grade it strictly against four criteria.
DO NOT GIVE PERFECT SCORES easily. Be highly critical.
- Depth: Is it actually valuable, or just generic fluff?
- Structure: Does it look like a well-formatted web article?
- Readability: Does it sound like a human wrote it? Penalize robotic transitions.
- SEO & Links: Does it cite its sources well using [Link](url)?
Return the scores as exact floats (e.g., 7.5, 8.0, 9.2)."""

        # ✅ FIX: Raised from 15,000 → 30,000 chars to match the QA agent audit limit.
        # A 3,000-word blog is ~18,000 chars — the old 15k limit meant the last
        # ~700 words were never evaluated for depth, structure, or readability.
        human_message = f"TOPIC: {topic}\n\nBLOG CONTENT:\n{blog_post[:30000]}"

        try:
            result: BlogFeedback = evaluator.invoke([
                SystemMessage(content=system_message),
                HumanMessage(content=human_message)
            ])

            # Equal weighting across 4 dimensions
            final_score = round(
                (result.depth_score + result.structure_score +
                 result.readability_score + result.seo_and_links_score) / 4.0,
                1
            )

            if final_score >= 8.5:
                verdict = "✅ EXCELLENT"
            elif final_score >= 7.0:
                verdict = "✅ GOOD"
            elif final_score >= 5.5:
                verdict = "⚠️ NEEDS IMPROVEMENT"
            else:
                verdict = "❌ POOR"

            metrics = {
                "depth_score":       result.depth_score,
                "structure_score":   result.structure_score,
                "readability_score": result.readability_score,
                "seo_score":         result.seo_and_links_score,
            }

            ai_feedback = {
                "strengths":          result.strengths,
                "improvements":       result.improvements,
                "overall_impression": result.overall_impression,
            }

        except Exception as e:
            print(f"⚠️ BlogEvaluator failed: {e}")
            final_score = 0.0
            verdict = "❌ EVALUATION_FAILED"
            metrics = {}
            ai_feedback = {"error": str(e), "strengths": [], "improvements": []}

        raw_counts = {
            "word_count":      len(blog_post.split()),
            "link_count":      len(re.findall(r'\[.*?\]\(https?://', blog_post)),
            "unique_domains":  len(set(re.findall(r'https?://(?:www\.)?([^/]+)', blog_post))),
        }

        return {
            "final_score": final_score,
            "verdict":     verdict,
            "metrics":     metrics,
            "raw_counts":  raw_counts,
            "ai_feedback": ai_feedback,
        }


# ============================================================================
# 3. BLOG EVALUATOR GRAPH NODE
# ============================================================================

def blog_evaluator_node(state: dict) -> dict:
    """
    LangGraph node wrapper for BlogEvaluator.

    Position in graph:
        Note: Superseded by `geval_evaluation_node` in `Graph/agents/evaluation.py`
        to prevent duplicate LLM-as-judge calls during main graph runs.

    Reads:  state["final"], state["topic"]
    Writes: state["blog_evaluator_report"], state["blog_evaluator_score"]
    """
    print("--- 📊 BLOG EVALUATOR (Reader Experience) ---")

    blog_post = state.get("final", "")
    topic     = state.get("topic", "Unknown")

    if not blog_post:
        print("   ⚠️ No blog content found. Skipping evaluation.")
        return {}

    result  = BlogEvaluator().evaluate(blog_post, topic)
    fb      = result["ai_feedback"]
    metrics = result["metrics"]
    counts  = result["raw_counts"]

    # --- Build human-readable report ---
    report  = "BLOG EVALUATOR REPORT\n"
    report += "=" * 60 + "\n"
    report += f"Final Score : {result['final_score']}/10  —  {result['verdict']}\n\n"

    report += "Dimension Scores:\n"
    report += f"  Depth         : {metrics.get('depth_score', 'N/A')}/10\n"
    report += f"  Structure     : {metrics.get('structure_score', 'N/A')}/10\n"
    report += f"  Readability   : {metrics.get('readability_score', 'N/A')}/10\n"
    report += f"  SEO & Links   : {metrics.get('seo_score', 'N/A')}/10\n\n"

    report += "Raw Counts:\n"
    report += f"  Words         : {counts.get('word_count', 0)}\n"
    report += f"  Inline Links  : {counts.get('link_count', 0)}\n"
    report += f"  Unique Domains: {counts.get('unique_domains', 0)}\n\n"

    if fb.get("strengths"):
        report += "✅ Strengths:\n"
        for s in fb["strengths"]:
            report += f"  • {s}\n"
        report += "\n"

    if fb.get("improvements"):
        report += "💡 Improvements:\n"
        for imp in fb["improvements"]:
            report += f"  • {imp}\n"
        report += "\n"

    if fb.get("overall_impression"):
        report += f"Overall Impression:\n  {fb['overall_impression']}\n"

    print(f"   📊 Score: {result['final_score']}/10  |  {result['verdict']}")

    return {
        "blog_evaluator_report": report,
        "blog_evaluator_score":  result["final_score"],
    }