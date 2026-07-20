import logging
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from Graph.state import State
from Graph.agents.utils import llm_quality, _job, _emit

logger = logging.getLogger("blog_pipeline")

# ============================================================================
# 1. STRUCTURED SCHEMAS FOR JUDGE RESPONSES
# ============================================================================

class CriteriaEvaluation(BaseModel):
    score: int = Field(
        ..., 
        description="Rating from 1 (poor) to 5 (excellent) according to the rubric criteria."
    )
    reasoning: str = Field(
        ..., 
        description="Clear explanation referencing the content, strengths, or specific failure points."
    )

class GEvalScorecard(BaseModel):
    coherence: CriteriaEvaluation = Field(
        ..., 
        description="Structure and logical flow. Are sections connected by smooth transitions?"
    )
    relevance: CriteriaEvaluation = Field(
        ..., 
        description="Coverage of the topic. Does it address target search intent and key keywords?"
    )
    accuracy: CriteriaEvaluation = Field(
        ..., 
        description="Factual consistency and evidence usage. Does it make unsupported claims?"
    )
    tone_alignment: CriteriaEvaluation = Field(
        ..., 
        description="Match with requested tone (e.g. conversational, professional) and target audience."
    )
    overall_score: float = Field(
        ..., 
        description="Calculated weighted average score (1.0 to 5.0)."
    )

# ============================================================================
# 2. RUBRIC DEFINITIONS
# ============================================================================

GEVAL_SYSTEM_PROMPT = """You are an academic quality assurance evaluator and content judge.
Your task is to grade the provided blog post on a scale of 1 to 5 across four distinct dimensions:

1. COHERENCE (Structure & Flow)
   - 5: Flawless logical structure. Exceptional transitions between sections. No repetitive sentences.
   - 3: Moderate flow. Basic section headers, but transitions feel abrupt or repetitive.
   - 1: Disjointed fragments, contradictory statements, or zero structural hierarchy.

2. RELEVANCE (Topic & Intent Coverage)
   - 5: Directly answers the requested topic. Integrates keywords naturally. Thoroughly covers user intent.
   - 3: Covers the main topic but misses critical angles or includes unrelated filler content.
   - 1: Off-topic or fails to address the requested subject.

3. ACCURACY & GROUNDING (Factual Entailment)
   - 5: Fully grounded. Every major factual claim or citation maps precisely to the provided research evidence.
   - 3: Mostly correct, but has minor unsupported claims or citations that aren't fully backed by the source details.
   - 1: Severe hallucinations, fabricated facts, or source stuffing.

4. TONE ALIGNMENT (Audience Match)
   - 5: Perfectly maintains the requested target tone and sounds extremely human and polished.
   - 3: Slightly robotic or drifts in tone (e.g., mixing highly technical terms in a casual guide).
   - 1: Fails the target tone entirely or sounds like generic AI filler (e.g., 'dive in', 'testament', 'in conclusion').

Scoring Guideline:
- Do NOT give perfect 5s unless the content is exceptional. Be critical and rigorous.
- The overall_score must be a weighted score: 30% Coherence, 20% Relevance, 30% Accuracy, 20% Tone.
- Output your evaluation using the requested structured output format."""

# ============================================================================
# 3. GRAPH NODE
# ============================================================================

def geval_evaluation_node(state: State) -> Dict[str, Any]:
    """
    LangGraph node that runs G-Eval validation on the compiled blog.
    
    Reads:
      - state["final"]: Generated Markdown content
      - state["topic"]: Target topic
      - state["target_tone"]: Desired tone
      - state["evidence"]: Research source packages
      
    Writes:
      - state["geval_scores"]: Serialized JSON structure of GEvalScorecard
    """
    job_id = _job(state)
    logger.info(f"[{job_id}] --- 📊 G-EVAL EVALUATION NODE (LLM-as-Judge) ---")
    _emit(job_id, "geval_evaluator", "working", "Analyzing quality using G-Eval academic scoring rubrics...")

    blog_content = state.get("final", "")
    topic = state.get("topic", "")
    target_tone = state.get("target_tone", "professional")
    evidence_items = state.get("evidence", [])

    if not blog_content:
        logger.warning(f"[{job_id}] No blog content found. Skipping G-Eval.")
        return {}

    # Format evidence for grounding evaluation.
    # Evidence items may be Pydantic `EvidenceItem` objects, plain dicts, or
    # raw strings — handle each shape without relying on `.get()` on models.
    formatted_evidence = ""
    for idx, item in enumerate(evidence_items):
        if isinstance(item, str):
            title, snippet = "Source", item
        elif isinstance(item, dict):
            title = item.get("title", "Unknown Source")
            snippet = item.get("snippet", "")
        else:
            title = getattr(item, "title", "Unknown Source")
            snippet = getattr(item, "snippet", "")
        formatted_evidence += f"\n[Evidence Source {idx+1}]: {title}\nExcerpt: {snippet}\n"

    human_prompt = f"""EVALUATION CONTEXT:
Topic: {topic}
Target Tone: {target_tone}

RESEARCH EVIDENCE PROVIDED TO THE WRITER:
{formatted_evidence[:8000]}

BLOG CONTENT UNDER EVALUATION:
{blog_content[:25000]}
"""

    try:
        # Request structured output from the quality model
        judge = llm_quality.with_structured_output(GEvalScorecard)
        scorecard: GEvalScorecard = judge.invoke([
            SystemMessage(content=GEVAL_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt)
        ])

        # Serialize scorecard into dictionary format
        scores_dict = scorecard.model_dump()
        logger.info(f"[{job_id}] G-Eval complete. Overall Score: {scorecard.overall_score}/5.0")
        
        _emit(job_id, "geval_evaluator", "completed", "G-Eval analysis finished successfully.", {
            "overall_score": scorecard.overall_score,
            "scores": scores_dict
        })

        return {
            "geval_scores": scores_dict
        }

    except Exception as e:
        logger.exception(f"[{job_id}] G-Eval node failed: {e}")
        _emit(job_id, "geval_evaluator", "error", f"G-Eval failed: {str(e)}")
        return {}


# ============================================================================
# 4. DEEPEVAL (OFFICIAL G-EVAL IMPLEMENTATION, Liu et al. 2023)
# ============================================================================
# Runs the same 4 rubrics through the `deepeval` library's `GEval` metric,
# which implements the chain-of-thought + form-filling protocol from the
# original paper. Scores are normalized to a 0.0–1.0 range (deepeval default)
# so they are NOT directly comparable to the 1–5 in-house scores above. Both
# are stored side-by-side so the FYP report can cite the academic metric.

def deepeval_evaluation_node(state: State) -> Dict[str, Any]:
    """
    LangGraph node that runs the official `deepeval` G-Eval metric on the
    compiled blog post across 4 academic rubrics (Coherence, Relevance,
    Accuracy/Grounding, Tone Alignment).

    Writes:
      - state["deepeval_scores"]: dict of {criterion: {score: float, reasoning: str}}
        plus "overall_score" (mean of the four 0–1 scores).
    """
    job_id = _job(state)
    logger.info(f"[{job_id}] --- 🎓 DEEPEVAL G-EVAL NODE (Liu et al. 2023) ---")
    _emit(job_id, "deepeval_evaluator", "working", "Running official deepeval G-Eval rubrics...")

    blog_content = state.get("final", "")
    topic = state.get("topic", "")
    target_tone = state.get("target_tone", "professional")
    evidence_items = state.get("evidence", [])

    if not blog_content:
        logger.warning(f"[{job_id}] No blog content found. Skipping deepeval G-Eval.")
        return {}

    # Lazy import so the rest of the pipeline still works if deepeval is missing.
    try:
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except ImportError as e:
        msg = f"deepeval not installed ({e}). Run: pip install deepeval"
        logger.warning(f"[{job_id}] {msg}")
        _emit(job_id, "deepeval_evaluator", "error", msg)
        return {}

    # Build retrieval_context from evidence (deepeval expects List[str])
    retrieval_context = []
    for item in evidence_items:
        if isinstance(item, str):
            retrieval_context.append(item)
            continue
        title = getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else None) or "Unknown Source"
        snippet = getattr(item, "snippet", None) or (item.get("snippet") if isinstance(item, dict) else None) or ""
        retrieval_context.append(f"{title}: {snippet}")

    # Truncate to keep token usage bounded (deepeval calls the judge LLM per metric)
    test_case = LLMTestCase(
        input=f"Write a {target_tone} blog post about: {topic}",
        actual_output=blog_content[:25000],
        retrieval_context=(retrieval_context or None),
    )

    metrics = {
        "coherence": GEval(
            name="Coherence",
            criteria=(
                "Evaluate the structural flow and logical progression of 'actual_output'. "
                "Reward smooth transitions between sections, a clear hierarchy, and absence "
                "of repetition or disjointed fragments. Penalize abrupt jumps and contradictions."
            ),
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        ),
        "relevance": GEval(
            name="Relevance",
            criteria=(
                "Determine whether 'actual_output' directly addresses the topic stated in "
                "'input', integrates relevant keywords naturally, and thoroughly covers the "
                "user's likely search intent. Penalize off-topic filler."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        ),
        "accuracy": GEval(
            name="Accuracy and Grounding",
            criteria=(
                "Check whether the factual claims, statistics, and citations in 'actual_output' "
                "are supported by 'retrieval_context'. Penalize hallucinations, fabricated facts, "
                "and unsupported numeric claims. Reward precise mapping of claims to sources."
            ),
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        ),
        "tone_alignment": GEval(
            name="Tone Alignment",
            criteria=(
                f"Assess whether 'actual_output' consistently matches the requested tone: "
                f"'{target_tone}'. Penalize generic AI-filler phrases (e.g., 'dive in', "
                f"'testament to', 'in conclusion', 'in today's fast-paced world') and robotic phrasing."
            ),
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        ),
    }

    results: Dict[str, Any] = {}
    for key, metric in metrics.items():
        try:
            metric.measure(test_case)
            results[key] = {
                "score": float(metric.score) if metric.score is not None else None,
                "reasoning": getattr(metric, "reason", "") or "",
            }
            logger.info(f"[{job_id}]   deepeval {key}: {results[key]['score']}")
        except Exception as e:
            logger.exception(f"[{job_id}] deepeval metric '{key}' failed: {e}")
            results[key] = {"score": None, "reasoning": f"deepeval error: {e}"}

    valid = [v["score"] for v in results.values() if isinstance(v, dict) and v.get("score") is not None]
    overall = round(sum(valid) / len(valid), 3) if valid else 0.0
    results["overall_score"] = overall

    logger.info(f"[{job_id}] deepeval G-Eval complete. Overall (0-1): {overall}")
    _emit(job_id, "deepeval_evaluator", "completed", "deepeval G-Eval finished.", {
        "overall_score": overall,
        "scores": results,
    })

    return {"deepeval_scores": results}
