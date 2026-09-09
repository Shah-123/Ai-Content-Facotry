import os
import sys
import json
import re
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 encoding for stdout/stderr to prevent CP1252/charmap crashes on Windows when printing emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Environment Setup — load .env but do NOT sys.exit here; api.py loads
# the key at runtime. The CLI path validates inside run_app() instead.
load_dotenv()

# LangGraph Imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

# Internal Imports
from Graph.state import State, Plan
from Graph.nodes import (
    router_node,
    research_node,
    orchestrator_node,
    worker_node,
    fanout,
    merge_content,
    decide_images,
    generate_and_place_images,
    qa_agent_node,
    revision_node,
    campaign_generator_node,
    video_generator_node,
    podcast_node,
    document_ingest_node,
    geval_evaluation_node,
    deepeval_evaluation_node,
    _safe_slug
)
from Graph.agents.topic_guard import evaluate_topic
from Graph.agents.revision import MAX_REVISIONS
from Graph.keyword_optimizer import keyword_optimizer_node
from Graph.completion_validator import validate_completion
from exporters import export_all

import logging
logger = logging.getLogger("blog_pipeline")


# ===========================================================================
# 1. HELPER FUNCTIONS
# ===========================================================================

def create_blog_structure(topic: str) -> dict:
    """Creates organized folder structure for the blog."""
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = _safe_slug(topic)[:50]
    backend_dir = Path(__file__).resolve().parent
    base_folder = str((backend_dir / "blogs" / f"{safe_topic}_{timestamp}").resolve()).replace("\\", "/")

    folders = {
        "base":     base_folder,
        "content":  f"{base_folder}/content",
        "social":   f"{base_folder}/social_media",
        "reports":  f"{base_folder}/reports",
        "assets":   f"{base_folder}/assets/images",
        "research": f"{base_folder}/research",
        "audio":    f"{base_folder}/audio",
        "video":    f"{base_folder}/video",
        "metadata": f"{base_folder}/metadata"
    }

    for path in folders.values():
        Path(path).mkdir(parents=True, exist_ok=True)

    return folders


def refine_plan_with_llm(current_plan: Plan, feedback: str) -> Plan:
    """Refines the plan based on human feedback."""
    print(f"\n   🤖 Refining plan based on: '{feedback}'...")
    llm    = ChatOpenAI(model="gpt-5-mini", temperature=0)
    editor = llm.with_structured_output(Plan)

    return editor.invoke([
        SystemMessage(content="You are a helpful editor. Update the Plan based STRICTLY on user feedback."),
        HumanMessage(content=f"Current Plan:\n{current_plan.model_dump_json()}\n\nFeedback: {feedback}")
    ])


def generate_readme(folders: dict, saved_files: dict, state: State) -> str:
    """Generates a README.md summarizing the generation run."""
    topic      = state.get("topic", "Unknown Topic")
    tone       = state.get("target_tone", "N/A")
    keywords   = state.get("target_keywords", [])
    qa_score   = state.get("qa_score", "N/A")
    eval_score = state.get("blog_evaluator_score", "N/A")
    word_count = len(state.get("final", "").split())
    blog_file  = os.path.basename(saved_files.get("blog", "blog.md"))

    plan     = state.get("plan")
    audience = plan.audience if plan and hasattr(plan, "audience") else "General"

    # ✅ FIX: Prepend a DRAFT banner when QA detected critical issues.
    # Previously the blog was silently saved as complete even when qa_verdict
    # was NEEDS_REVISION. Now the README opens with a loud, unmissable warning.
    draft_banner = ""
    if _qa_needs_review(state):
        critical_issues = [
            i for i in state.get("qa_issues", []) if i.get("severity") == "critical"
        ]
        issue_lines = "\n".join(
            f"- **{i.get('issue_type', 'unknown').upper()}**: {i.get('claim', '')[:120]}"
            for i in critical_issues
        )
        draft_banner = f"""## ⚠️ DRAFT — NOT READY TO PUBLISH

> **QA detected {len(critical_issues)} critical issue(s). Review and fix before publishing.**

{issue_lines}

---

"""

    md = f"""# {topic}

{draft_banner}## 📋 Blog Information
- **Topic**: {topic}
- **Generated Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Target Audience**: {audience}
- **Tone**: {tone}
- **Word Count**: {word_count}

## 📁 Folder Structure
```
{os.path.basename(folders['base'])}/
├── content/
│   └── {blog_file}
├── social_media/
├── reports/
│   ├── qa_report.txt
│   ├── blog_evaluator_report.txt
│   └── keyword_optimization.txt
├── research/
│   └── evidence.json
├── assets/images/
├── audio/
├── video/
└── metadata/
    ├── plan.json
    └── metadata.json
```

## 📊 Quality Metrics

{state.get('qa_report', 'No QA report available')}

---

### QA Score: {qa_score}/10
### Blog Evaluator Score: {eval_score}/10

## 🎯 SEO Details
- **Target Keywords**: {', '.join(keywords) if keywords else 'None specified'}
- **Tone**: {tone}
- **Mode**: {state.get("mode")}
- **Evidence Sources**: {len(state.get("evidence", []))}

## ⚙️ Generation Details
- **Mode**: {state.get("mode")}
- **Research Queries**: {len(state.get("queries", []))}
- **Evidence Sources**: {len(state.get("evidence", []))}

---
*Generated by AI Content Factory*
"""
    readme_path = f"{folders['base']}/README.md"
    Path(readme_path).write_text(md, encoding="utf-8")
    return readme_path


def save_blog_content(folders: dict, state: State) -> dict:
    """Saves all outputs to their respective folders."""
    saved = {}
    plan  = state.get("plan")
    if not plan:
        return saved

    slug = _safe_slug(plan.blog_title)

    # 1. Content
    if state.get("final"):
        path = f"{folders['content']}/{slug}.md"
        blog_content = state["final"]

        # ✅ FIX: Prepend a DRAFT banner to the actual blog file when QA
        # detected critical issues, so the user sees it before publishing.
        if _qa_needs_review(state):
            critical_issues = [
                i for i in state.get("qa_issues", []) if i.get("severity") == "critical"
            ]
            issue_lines = "\n".join(
                f"> - **{i.get('issue_type','unknown').upper()}**: {i.get('claim','')[:120]}"
                for i in critical_issues
            )
            draft_header = (
                f"> ## ⚠️ DRAFT — NOT READY TO PUBLISH\n"
                f"> QA flagged {len(critical_issues)} critical issue(s):\n"
                f"{issue_lines}\n\n---\n\n"
            )
            blog_content = draft_header + blog_content

        Path(path).write_text(blog_content, encoding="utf-8")
        saved["blog"] = path
        print(f"   ✅ Saved blog: {os.path.basename(path)}")

        # Export to additional formats (HTML, PDF, DOCX)
        requested_formats = state.get("export_formats", [])
        if requested_formats:
            blog_title = plan.blog_title if plan else "blog"
            base_export_path = f"{folders['content']}/{slug}"
            export_results = export_all(blog_content, base_export_path, blog_title, requested_formats)
            for fmt, fmt_path in export_results.items():
                if fmt_path:
                    saved[f"blog_{fmt}"] = fmt_path
                    print(f"   ✅ Exported {fmt.upper()}: {os.path.basename(fmt_path)}")

    # 2. Campaign Assets
    # Only the channels campaign_generator_node actually produces. Entries for
    # facebook / youtube / email / landing_page were removed with their state
    # fields — they mapped to keys the node always left empty.
    platform_map = {
        "linkedin":    ("linkedin_post",  "txt"),
        "twitter":     ("twitter_thread", "md"),
    }
    for platform, (key, ext) in platform_map.items():
        if state.get(key):
            path = f"{folders['social']}/{platform}_{slug}.{ext}"
            Path(path).write_text(state[key], encoding="utf-8")
            saved[platform] = path

    # 3. Reports
    if state.get("qa_report"):
        path = f"{folders['reports']}/qa_report.txt"
        Path(path).write_text(state["qa_report"], encoding="utf-8")
        saved["qa_report"] = path

    if state.get("blog_evaluator_report"):
        path = f"{folders['reports']}/blog_evaluator_report.txt"
        Path(path).write_text(state["blog_evaluator_report"], encoding="utf-8")
        saved["blog_evaluator_report"] = path
        print(f"   ✅ Saved blog evaluator report")

    if state.get("geval_scores"):
        geval = state["geval_scores"]
        geval_report = f"""G-EVAL (LLM-AS-JUDGE) ACADEMIC REPORT
============================================================
Overall G-Eval Score: {geval.get('overall_score', 'N/A')}/5.0

Rubric Evaluations:
------------------------------------------------------------
1. COHERENCE: {geval.get('coherence', {}).get('score', 'N/A')}/5
   Reasoning: {geval.get('coherence', {}).get('reasoning', 'N/A')}

2. RELEVANCE: {geval.get('relevance', {}).get('score', 'N/A')}/5
   Reasoning: {geval.get('relevance', {}).get('reasoning', 'N/A')}

3. ACCURACY & GROUNDING: {geval.get('accuracy', {}).get('score', 'N/A')}/5
   Reasoning: {geval.get('accuracy', {}).get('reasoning', 'N/A')}

4. TONE ALIGNMENT: {geval.get('tone_alignment', {}).get('score', 'N/A')}/5
   Reasoning: {geval.get('tone_alignment', {}).get('reasoning', 'N/A')}
"""
        path = f"{folders['reports']}/geval_report.txt"
        Path(path).write_text(geval_report, encoding="utf-8")
        saved["geval_report"] = path
        print(f"   ✅ Saved G-Eval academic report")

    if state.get("deepeval_scores"):
        de = state["deepeval_scores"]
        deepeval_report = f"""DEEPEVAL G-EVAL REPORT (Liu et al. 2023)
============================================================
Library:        deepeval (official implementation)
Score Scale:    0.0 (worst) - 1.0 (best)
Overall Score:  {de.get('overall_score', 'N/A')}/1.0

Rubric Evaluations:
------------------------------------------------------------
1. COHERENCE: {de.get('coherence', {}).get('score', 'N/A')}/1.0
   Reasoning: {de.get('coherence', {}).get('reasoning', 'N/A')}

2. RELEVANCE: {de.get('relevance', {}).get('score', 'N/A')}/1.0
   Reasoning: {de.get('relevance', {}).get('reasoning', 'N/A')}

3. ACCURACY & GROUNDING: {de.get('accuracy', {}).get('score', 'N/A')}/1.0
   Reasoning: {de.get('accuracy', {}).get('reasoning', 'N/A')}

4. TONE ALIGNMENT: {de.get('tone_alignment', {}).get('score', 'N/A')}/1.0
   Reasoning: {de.get('tone_alignment', {}).get('reasoning', 'N/A')}
"""
        path = f"{folders['reports']}/deepeval_report.txt"
        Path(path).write_text(deepeval_report, encoding="utf-8")
        saved["deepeval_report"] = path
        print(f"   ✅ Saved deepeval (official G-Eval) report")

    # SEO metadata is publisher metadata, not article content, so it is written
    # here rather than appended to the post. Keeping it out of `final` also
    # means the QA auditor and the G-Eval/DeepEval judges score the article
    # itself instead of a metadata footer.
    if state.get("seo_metadata"):
        seo = state["seo_metadata"]
        rt = seo.get("reading_time_minutes")
        lines = [
            "SEO METADATA",
            "=" * 60,
            f"Estimated Reading Time: {rt} minute{'s' if rt != 1 else ''}",
            "",
        ]
        if seo.get("meta_title"):
            lines.append(f"Meta Title:       {seo['meta_title']}")
        if seo.get("meta_description"):
            lines.append(f"Meta Description: {seo['meta_description']}")
        primary = seo.get("primary_keywords") or []
        secondary = seo.get("secondary_keywords") or []
        if primary:
            lines.append(f"Primary Keywords:   {', '.join(primary)}")
        if secondary:
            lines.append(f"Secondary Keywords: {', '.join(secondary)}")
        faq = seo.get("faq") or []
        if faq:
            lines += ["", "FAQ (schema markup candidates):", "-" * 60]
            for i, item in enumerate(faq, 1):
                q = item.get("question", "") if isinstance(item, dict) else ""
                a = item.get("answer", "") if isinstance(item, dict) else ""
                lines += [f"{i}. {q}", f"   {a}", ""]

        path = f"{folders['reports']}/seo_metadata.txt"
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        saved["seo_metadata"] = path
        print(f"   ✅ Saved SEO metadata report")

    if state.get("keyword_report"):
        path = f"{folders['reports']}/keyword_optimization.txt"
        Path(path).write_text(state["keyword_report"], encoding="utf-8")
        saved["keyword_report"] = path

    if state.get("completion_report"):
        path = f"{folders['reports']}/completion_report.txt"
        Path(path).write_text(state["completion_report"], encoding="utf-8")
        saved["completion_report"] = path

    # 4. Audio
    if state.get("podcast_audio_path") and os.path.exists(state["podcast_audio_path"]) and os.path.getsize(state["podcast_audio_path"]) > 0:
        import shutil
        ext = os.path.splitext(state["podcast_audio_path"])[1] or ".wav"
        dest = f"{folders['audio']}/podcast{ext}"
        try:
            if not os.path.samefile(state["podcast_audio_path"], dest):
                shutil.copy(state["podcast_audio_path"], dest)
        except (OSError, ValueError):
            shutil.copy(state["podcast_audio_path"], dest)
        saved["podcast"] = dest

    # 5. Video
    if state.get("video_path") and os.path.exists(state["video_path"]) and os.path.getsize(state["video_path"]) > 0:
        import shutil
        dest = f"{folders['video']}/short.mp4"
        try:
            if not os.path.samefile(state["video_path"], dest):
                shutil.copy(state["video_path"], dest)
        except (OSError, ValueError):
            # samefile can raise if one path doesn't exist yet
            shutil.copy(state["video_path"], dest)
        saved["video"] = dest

    # 6. Research Evidence
    if state.get("evidence"):
        evidence_data = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in state["evidence"]
        ]
        path = f"{folders['research']}/evidence.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(evidence_data, f, indent=2)
        saved["evidence"] = path

    # 7. Metadata
    meta = {
        "topic":                 state.get("topic"),
        "as_of":                 state.get("as_of"),
        "mode":                  state.get("mode"),
        "generated_at":          datetime.now().isoformat(),
        "word_count":            len(state.get("final", "").split()),
        "target_tone":           state.get("target_tone"),
        "target_keywords":       state.get("target_keywords", []),
        "num_images":            state.get("num_images", 2),
        "generate_images":       state.get("generate_images", True),
        "image_model":           state.get("image_model", "dall-e-3"),
        "image_size":            state.get("image_size", "1024x1024"),
        "image_quality":         state.get("image_quality", "standard"),
        "image_style":           state.get("image_style", "vivid"),
        "qa_score":              state.get("qa_score"),
        "qa_verdict":            state.get("qa_verdict"),
        "blog_evaluator_score":  state.get("blog_evaluator_score"),
        "geval_scores":          state.get("geval_scores"),
        "deepeval_scores":       state.get("deepeval_scores"),
        "seo_metadata":          state.get("seo_metadata"),
        "file_paths": {
            "blog":                  saved.get("blog"),
            "qa_report":             saved.get("qa_report"),
            "blog_evaluator_report": saved.get("blog_evaluator_report"),
            "geval_report":          saved.get("geval_report"),
            "deepeval_report":       saved.get("deepeval_report"),
            "completion_report":     saved.get("completion_report"),
            "keyword_report":        saved.get("keyword_report"),
            "seo_metadata":          saved.get("seo_metadata"),
            "evidence":              saved.get("evidence"),
            "video":                 saved.get("video"),
            "podcast":               saved.get("podcast"),
            "plan":                  f"{folders['metadata']}/plan.json",
        }
    }

    with open(f"{folders['metadata']}/metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    if plan:
        with open(f"{folders['metadata']}/plan.json", "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, indent=2)

    return saved


# ===========================================================================
# 2. BUILD GRAPH
# ===========================================================================

# (Removed _after_qa)

def _qa_needs_review(state: State) -> bool:
    """Returns True if QA detected critical issues that require human review."""
    if state.get("qa_verdict", "READY") != "NEEDS_REVISION":
        return False
    issues = state.get("qa_issues", [])
    return any(i.get("severity") == "critical" for i in issues)


def build_graph(memory=None):
    """Build the LangGraph workflow with all nodes."""

    if memory is None:
        memory = MemorySaver()

    # --- Subgraph: Reducer ---
    reducer = StateGraph(State)
    reducer.add_node("merge_content",             merge_content)
    reducer.add_node("decide_images",             decide_images)
    reducer.add_node("generate_and_place_images", generate_and_place_images)
    reducer.add_edge(START, "merge_content")

    reducer.add_conditional_edges(
        "merge_content",
        lambda s: "decide_images" if s.get("generate_images", True) else END
    )
    reducer.add_edge("decide_images",             "generate_and_place_images")
    reducer.add_edge("generate_and_place_images", END)

    # --- Main Graph ---
    workflow = StateGraph(State)

    workflow.add_node("router",               router_node)
    workflow.add_node("document_ingest",      document_ingest_node)
    workflow.add_node("research",             research_node)
    workflow.add_node("orchestrator",         orchestrator_node)
    workflow.add_node("worker",               worker_node)
    workflow.add_node("reducer",              reducer.compile())
    workflow.add_node("completion_validator", validate_completion)
    workflow.add_node("qa_agent",             qa_agent_node)
    workflow.add_node("revision",              revision_node)
    workflow.add_node("keyword_optimizer",    keyword_optimizer_node)
    workflow.add_node("geval_evaluator",       geval_evaluation_node)
    # NOTE: `deepeval_evaluator` is NOT wired into the graph.
    # The official deepeval G-Eval (Liu et al. 2023) makes 4 extra LLM calls
    # per blog, so it runs ON DEMAND from the UI ("Run Academic Audit" button)
    # via the POST /api/jobs/{job_id}/run-deepeval endpoint.
    workflow.add_node("campaign_generator",   campaign_generator_node)
    workflow.add_node("video_generator",      video_generator_node)
    workflow.add_node("podcast_generator",    podcast_node)

    # --- Edges ---
    workflow.add_edge(START, "router")

    # ✅ Document Upload Routing:
    # If the job carries an upload_id, run document_ingest first to load
    # pre-extracted evidence (and optionally derive the topic).  Then:
    #   - source_mode == "closed_book" → straight to orchestrator (no web)
    #   - otherwise ("hybrid"|"auto_topic") → research_node, which now
    #     MERGES web evidence on top of doc evidence instead of replacing.
    def _after_router(s: State) -> str:
        if s.get("upload_id"):
            return "document_ingest"
        return "research" if s.get("needs_research") else "orchestrator"

    workflow.add_conditional_edges(
        "router",
        _after_router,
        ["document_ingest", "research", "orchestrator"],
    )

    def _after_ingest(s: State) -> str:
        mode = (s.get("source_mode") or "hybrid").lower()
        if mode == "closed_book":
            return "orchestrator"
        # hybrid / auto_topic both want web research too
        return "research"

    workflow.add_conditional_edges(
        "document_ingest",
        _after_ingest,
        ["orchestrator", "research"],
    )

    workflow.add_edge("research",             "orchestrator")
    workflow.add_conditional_edges("orchestrator", fanout, ["worker"])
    workflow.add_edge("worker",               "reducer")
    workflow.add_edge("reducer",              "completion_validator")
    
    # Conditional edge from completion_validator
    workflow.add_conditional_edges(
        "completion_validator",
        lambda s: "qa_agent" if s.get("generate_qa", False) else "keyword_optimizer"
    )

    # ✅ Automated Revision Loop:
    # qa_agent → _after_qa routes to either:
    #   - "revision" (critical issues + under max) → loops back to qa_agent
    #   - "keyword_optimizer" (READY or max revisions reached)
    # Uses the single source of truth MAX_REVISIONS from revision.py
    # (imported at the top of this module) — previously this file
    # redefined its own MAX_MANUAL_REVISIONS=1 which drifted from the
    # documented behaviour.
    def _after_qa_manual(state: State) -> str:
        verdict = state.get("qa_verdict", "READY")
        issues = state.get("qa_issues", [])
        revision_count = state.get("revision_count", 0)

        if verdict == "NEEDS_REVISION":
            critical = [i for i in issues if i.get("severity") == "critical"]
            if critical and revision_count < MAX_REVISIONS:
                return "revision"
        return "keyword_optimizer"

    workflow.add_conditional_edges(
        "qa_agent",
        _after_qa_manual,
        ["revision", "keyword_optimizer"]
    )
    workflow.add_edge("revision", "qa_agent")  # ← the feedback loop

    workflow.add_edge("keyword_optimizer", "geval_evaluator")

    def after_evaluator_router(s):
        destinations = []
        if s.get("generate_campaign", True):
            destinations.append("campaign_generator")
        if s.get("generate_video", True):
            destinations.append("video_generator")
        if s.get("generate_podcast", True):
            destinations.append("podcast_generator")
        return destinations if destinations else END

    workflow.add_conditional_edges(
        "geval_evaluator",
        after_evaluator_router,
        ["campaign_generator", "video_generator", "podcast_generator", END]
    )

    workflow.add_edge("campaign_generator", END)
    workflow.add_edge("video_generator",    END)
    workflow.add_edge("podcast_generator",  END)

    return workflow.compile(
        checkpointer=memory,
        interrupt_after=["orchestrator"]
    )


# ===========================================================================
# 3. MAIN RUNNER
# ===========================================================================

def run_app(
    topic: str = None,
    tone: str = None,
    sections: int = None,
    human_in_loop: bool = False,
    include_video: bool = False,
    include_podcast: bool = False,
    include_campaign: bool = False,
    job_id: str = None,
):
    """
    Main entry point for both CLI and API execution.

    When called from the CLI (no arguments), uses interactive prompts.
    When called from the API (arguments provided), skips prompts entirely
    so the Streamlit dashboard can drive generation programmatically.

    Parameters
    ----------
    topic          : Blog topic string (API mode) or None (CLI prompts user).
    tone           : Tone string e.g. "professional" (API) or None (CLI picks).
    sections       : Number of body sections (API) or None (CLI picks).
    human_in_loop  : If True, halt at plan stage for HITL review (API flag).
    include_video  : Enable video generation.
    include_podcast: Enable podcast generation.
    include_campaign: Enable social media campaign generation.
    job_id         : Job UUID supplied by the API for event bus tracking.
    """
    # -----------------------------------------------------------------------
    # Determine execution mode
    # -----------------------------------------------------------------------
    api_mode = topic is not None  # API supplied a topic → skip all prompts

    print("=" * 80)
    print("🚀 AI CONTENT FACTORY (FYP EDITION)")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # 1. Topic input & validation
    # -----------------------------------------------------------------------
    if not api_mode:
        topic = input("\n📝 Enter blog topic: ").strip()
        if not topic:
            return

    verdict = evaluate_topic(topic)
    if not verdict.is_safe:
        print(f"❌ Rejected: {verdict.reason}")
        return

    print(f"✅ Topic Accepted: {topic}")

    # -----------------------------------------------------------------------
    # 2. Tone selection
    # -----------------------------------------------------------------------
    tone_map = {
        "1": "professional", "2": "conversational",
        "3": "technical",    "4": "educational",
        "5": "persuasive",   "6": "inspirational"
    }

    if not api_mode:
        print("\n🎨 Select Tone:")
        print("1. Professional (formal, data-driven)")
        print("2. Conversational (friendly, relatable)")
        print("3. Technical (precise, expert-level)")
        print("4. Educational (teaching-focused)")
        print("5. Persuasive (compelling, action-driven)")
        print("6. Inspirational (motivating, aspirational)")
        tone_choice = input("Choose (1-6) [default: 1]: ").strip() or "1"
        target_tone = tone_map.get(tone_choice, "professional")
    else:
        target_tone = tone or "professional"

    # -----------------------------------------------------------------------
    # 3. Keywords
    # -----------------------------------------------------------------------
    if not api_mode:
        keywords_input = input("\n🎯 Enter target keywords (comma-separated, or press Enter to skip): ").strip()
        target_keywords = [k.strip() for k in keywords_input.split(",")] if keywords_input else []
    else:
        target_keywords = []  # API doesn't expose keywords yet; can be extended

    # -----------------------------------------------------------------------
    # 4. Feature toggles
    # -----------------------------------------------------------------------
    if not api_mode:
        print("\n💰 Cost-Saving Options (Press Enter for Yes):")
        generate_images   = input("Generate Images (Gemini)? [Y/n]: ").strip().lower() != "n"
        generate_qa       = input("Run QA fact-check + revision loop? [Y/n]: ").strip().lower() != "n"
        generate_campaign = input("Generate Social Media Campaign? [Y/n]: ").strip().lower() != "n"
        generate_video    = input("Generate Short Video (Voiceover + Captions + Pexels)? [Y/n]: ").strip().lower() != "n"
        generate_podcast  = input("Generate Audio Podcast (Gemini)? [Y/n]: ").strip().lower() != "n"
    else:
        generate_images   = True  # always generate images in API mode
        generate_qa       = True
        generate_campaign = include_campaign
        generate_video    = include_video
        generate_podcast  = include_podcast
        export_formats    = ["html"]  # API mode: always export HTML for frontend

    # -----------------------------------------------------------------------
    # 5. Export format selection
    # -----------------------------------------------------------------------
    if not api_mode:
        print("\n📦 Export Formats (blog will always be saved as Markdown):")
        print("1. Markdown only")
        print("2. Markdown + HTML")
        print("3. Markdown + HTML + PDF")
        print("4. Markdown + HTML + DOCX")
        print("5. All formats (MD + HTML + PDF + DOCX)")
        export_choice = input("Choose (1-5) [default: 2]: ").strip() or "2"
        export_map = {
            "1": [],
            "2": ["html"],
            "3": ["html", "pdf"],
            "4": ["html", "docx"],
            "5": ["html", "pdf", "docx"],
        }
        export_formats = export_map.get(export_choice, ["html"])

    # -----------------------------------------------------------------------
    # 6. Number of sections
    # -----------------------------------------------------------------------
    if not api_mode:
        sections_input = input("\n📏 How many body sections? (1-10, plus intro & closing are added automatically) [default: 3]: ").strip()
        try:
            target_sections = max(1, min(10, int(sections_input))) if sections_input else 3
        except ValueError:
            target_sections = 3
    else:
        target_sections = max(1, min(10, sections)) if sections else 3

    from Graph.agents.orchestrator import TOTAL_FIXED_SECTIONS
    total_sections = target_sections + TOTAL_FIXED_SECTIONS
    print(f"\n✅ Tone: {target_tone}")
    print(f"✅ Sections: {target_sections} body + {TOTAL_FIXED_SECTIONS} fixed (intro/closing) = {total_sections} total")
    export_labels = ['MD'] + [f.upper() for f in export_formats] if export_formats else ['MD']
    print(f"✅ Options: Images={'ON' if generate_images else 'OFF'} | QA={'ON' if generate_qa else 'OFF'} | Campaign={'ON' if generate_campaign else 'OFF'} | Video={'ON' if generate_video else 'OFF'} | Podcast={'ON' if generate_podcast else 'OFF'}")
    print(f"✅ Export Formats: {' + '.join(export_labels)}")
    print(f"✅ Keywords: {', '.join(target_keywords) if target_keywords else 'None specified'}")

    # -----------------------------------------------------------------------
    # 6. Output folder structure
    # -----------------------------------------------------------------------
    folders = create_blog_structure(topic)
    print(f"📁 Working Directory: {folders['base']}")

    # -----------------------------------------------------------------------
    # 7. Build and configure the graph
    # -----------------------------------------------------------------------
    app    = build_graph()
    import uuid as _uuid
    thread = {"configurable": {"thread_id": f"job_{_uuid.uuid4().hex[:12]}"}}

    initial_state = {
        "topic":             topic,
        "as_of":             date.today().isoformat(),
        "sections":          [],
        "blog_folder":       folders["base"],
        "target_tone":       target_tone,
        "target_keywords":   target_keywords,
        "target_sections":   target_sections,
        "generate_images":   generate_images,
        "generate_qa":       generate_qa,
        "generate_campaign": generate_campaign,
        "generate_video":    generate_video,
        "generate_podcast":  generate_podcast,
        "export_formats":    export_formats,
        "_job_id":           job_id or "",
    }

    # -----------------------------------------------------------------------
    # 8. Phase 1: Research & Planning
    # -----------------------------------------------------------------------
    print("\n🚀 PHASE 1: RESEARCH & PLANNING")
    for _ in app.stream(initial_state, thread, stream_mode="values"):
        pass

    # -----------------------------------------------------------------------
    # 9. Human-in-the-Loop review (CLI always prompts; API only if requested)
    # -----------------------------------------------------------------------
    state = app.get_state(thread).values
    plan  = state.get("plan")

    print("\n" + "=" * 60)
    print(f"📋 DRAFT PLAN: {plan.blog_title}")
    print(f"🎨 Tone: {plan.tone}")
    if plan.primary_keywords:
        print(f"🎯 Keywords: {', '.join(plan.primary_keywords)}")
    print("=" * 60)

    for t in plan.tasks:
        keyword_tags = f" [{', '.join(t.tags[:2])}]" if t.tags else ""
        print(f"   {t.id + 1}. {t.title}{keyword_tags}")

    if not api_mode or human_in_loop:
        while True:
            feedback = input("\n✅ Approved? (y/n): ").lower()
            if feedback == "y":
                break
            elif feedback == "n":
                notes    = input("💬 Enter changes: ")
                new_plan = refine_plan_with_llm(plan, notes)
                app.update_state(thread, {"plan": new_plan})
                plan = new_plan
                print("\n✅ Plan Updated:")
                for t in plan.tasks:
                    print(f"   - {t.title}")
    else:
        # API mode (no HITL): auto-approve the plan
        print("\n⚡ API Mode: Auto-approving plan (human_in_loop=False)")

    # -----------------------------------------------------------------------
    # 10. Phase 2: Execution
    # -----------------------------------------------------------------------
    print("\n🚀 PHASE 2: WRITING & PRODUCTION")
    for _ in app.stream(None, thread, stream_mode="values", recursion_limit=150):
        pass

    # -----------------------------------------------------------------------
    # 11. Save outputs
    # -----------------------------------------------------------------------
    final_state = app.get_state(thread).values
    print("\n💾 SAVING ASSETS...")
    saved_files = save_blog_content(folders, final_state)
    readme      = generate_readme(folders, saved_files, final_state)

    print("\n" + "=" * 80)

    if _qa_needs_review(final_state):
        print("⚠️  GENERATION COMPLETE — DRAFT (NOT READY TO PUBLISH)")
        print("   QA detected critical issues. Review the blog before sharing.")
    else:
        print("✨ GENERATION COMPLETE ✨")

    print(f"📂 Output Folder: {folders['base']}")
    print(f"📖 Read Summary:  {readme}")

    qa_score   = final_state.get("qa_score", "N/A")
    qa_verdict = final_state.get("qa_verdict", "N/A")
    eval_score = final_state.get("blog_evaluator_score", "N/A")

    print(f"\n📊 QA Score:             {qa_score}/10  ({qa_verdict})")
    print(f"📊 Blog Evaluator Score: {eval_score}/10")

    if final_state.get("keyword_report"):
        print("\n" + "=" * 60)
        print(final_state["keyword_report"])

    if final_state.get("blog_evaluator_report"):
        print("\n" + "=" * 60)
        print(final_state["blog_evaluator_report"])

    print("=" * 80)

    # Emit completion event for API/Frontend tracking
    if job_id:
        try:
            from event_bus import events
            events.emit_sync(job_id, "system", "completed", "Generation finished successfully.", {
                "blog_folder": folders['base']
            })
        except Exception as e:
            print(f"Failed to emit completion event: {e}")


if __name__ == "__main__":
    run_app()
