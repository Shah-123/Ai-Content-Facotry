import operator
from typing import Annotated, List, Optional, TypedDict, Any
from pydantic import BaseModel, Field

# ============================================================================
# 1. PYDANTIC MODELS (LLM STRUCTURED OUTPUTS)
# ============================================================================

class RouterDecision(BaseModel):
    """Output schema for the Router Node."""
    needs_research: bool = Field(description="True if the topic requires external search info.")
    mode: str = Field(description="One of: 'closed_book', 'hybrid', 'open_book'")
    reason: str = Field(description="Short explanation of the decision")
    queries: List[str] = Field(description="3-5 search queries if research is needed", default=[])

class EvidenceItem(BaseModel):
    """Schema for a single piece of research evidence."""
    title: str = Field(description="Title of the source")
    url: str = Field(description="URL of the source")
    snippet: str = Field(description="Relevant content excerpt")
    published_at: Optional[str] = Field(description="Date string or None")
    source: str = Field(description="Domain name (e.g. techcrunch.com)")
    authors: Optional[str] = Field(description="Author Names or Organization", default=None)

class EvidencePack(BaseModel):
    """Container for search results."""
    evidence: List[EvidenceItem]

class Task(BaseModel):
    """Schema for a single section writing task."""
    id: int = Field(description="Sequential ID (0, 1, 2...)")
    title: str = Field(description="Section H2 Title")
    goal: str = Field(description="What the reader should learn")
    bullets: List[str] = Field(description="Key points to cover")
    target_words: int = Field(default=350, description="Approx word count (default 350)")
    tags: List[str] = Field(description="SEO tags for this section", default=[])

    # ✅ FIX: Evidence distribution.
    # The orchestrator assigns a slice of the evidence list to each task
    # after plan generation (see orchestrator.py → _assign_evidence_to_tasks).
    # fanout() in workers.py reads these indices and sends only the assigned
    # slice to each worker, preventing all workers from pulling the same
    # stats and repeating them across every section.
    # Default is empty list — if no assignment was made, workers fall back
    # to the full evidence list (safe backward-compatible default).
    assigned_evidence_indices: List[int] = Field(
        default=[],
        description="Indices into the global evidence list assigned to this section"
    )

class Plan(BaseModel):
    """Schema for the entire blog outline."""
    blog_title: str = Field(description="SEO-optimized H1 title")
    tone: str = Field(description="Tone of voice (e.g., 'professional', 'conversational')")
    audience: str = Field(description="Target audience")
    tasks: List[Task] = Field(description="List of sections to write")

    # Keyword optimization fields
    primary_keywords: List[str] = Field(
        description="Main SEO keywords to optimize for",
        default=[]
    )
    keyword_strategy: str = Field(
        description="How keywords will be distributed across sections",
        default=""
    )

class ImageSpec(BaseModel):
    """Schema for a single image generation request."""
    target_paragraph: str = Field(description="The exact first 5 words of the paragraph after which this image should be inserted")
    filename: str = Field(description="dashed-slug-filename")
    prompt: str = Field(description="Detailed prompt for the image generator")
    alt: str = Field(description="Alt text for accessibility")
    caption: str = Field(description="Caption to display below the image")

class GlobalImagePlan(BaseModel):
    """Schema for the image placement strategy."""
    images: List[ImageSpec] = Field(description="List of images to generate")


# ============================================================================
# 2. GRAPH STATE (THE MEMORY)
# ============================================================================

class State(TypedDict, total=False):
    """
    The central memory state of the graph.
    'total=False' allows keys to be missing during initialization.
    """

    # --- Internal ---
    _job_id: str        # For real-time event emission

    # --- Inputs ---
    topic: str
    as_of: str          # Date string
    blog_folder: str    # Path to save outputs
    target_tone: Optional[str]        # e.g., "professional", "conversational"
    target_keywords: List[str]        # e.g., ["AI healthcare", "medical automation"]
    target_sections: int              # How many body sections to generate

    # --- Document Upload (optional) ---
    # When set, a `document_ingest_node` runs before the orchestrator and
    # loads pre-extracted EvidenceItems from the upload's evidence.json.
    upload_id: Optional[str]
    source_mode: Optional[str]        # "closed_book" | "hybrid" | "auto_topic"
    document_filename: Optional[str]  # original filename for citations

    # --- Router Outputs ---
    needs_research: bool
    mode: str
    queries: List[str]
    recency_days: int

    # --- Research Outputs ---
    evidence: List[EvidenceItem]

    # --- Planning Outputs ---
    plan: Plan

    # --- Worker Outputs (Parallel) ---
    # CRITICAL: Annotated[..., operator.add] enables the "Fan-Out" pattern.
    # It tells LangGraph: "When multiple nodes return 'sections', append them
    # to this list instead of overwriting."
    sections: Annotated[List[tuple], operator.add]

    # --- Reducer/Merger Outputs ---
    merged_md: str            # Text combined from sections
    md_with_placeholders: str # Text with [[IMAGE_1]] tags

    # Note: We store dicts here because we use .model_dump() in nodes.py
    image_specs: List[dict]

    # --- Final Outputs ---
    final: str                # The finished Markdown blog post

    # --- Completion Validator ---
    completion_report: str
    completion_score: int
    completion_issues: List[dict]

    # --- Quality Assurance (QA) ---
    qa_report: str            # The text report from the QA Agent
    qa_verdict: str           # "READY" or "NEEDS_REVISION"
    qa_issues: List[dict]     # Structured list of flagged issues
    qa_score: float           # 0-10 overall score

    # --- Revision Loop ---
    revision_count: int       # How many QA → revision loops have run (starts 0, max 2)
    qa_fixed_claims: List[str]  # Claims already addressed by revision — prevents QA re-flagging

    # --- Blog Evaluator ---
    blog_evaluator_report: str   # Human-readable report with scores and feedback
    blog_evaluator_score: float  # 0-10 final score (average of 4 dimensions)

    # --- G-Eval Scorecard ---
    geval_scores: Optional[dict]  # In-house LLM-as-judge G-Eval (1–5 scale)

    # --- DeepEval (official Liu et al. 2023 G-Eval, 0–1 scale) ---
    deepeval_scores: Optional[dict]

    # --- Keyword Optimization ---
    keyword_analysis: dict      # Detailed keyword metrics
    keyword_report: str         # Human-readable report

    # --- Campaign Outputs ---
    linkedin_post: str
    youtube_script: str
    facebook_post: str
    email_sequence: str
    twitter_thread: str
    landing_page: str

    # --- Video & Audio Outputs ---
    video_path: Optional[str]          # Path to the finalized MP4 video
    podcast_audio_path: Optional[str]  # Path to the generated Gemini podcast audio
    whisper_model_size: Optional[str]  # Optional Whisper model size configuration

    # --- Cost Saving Flags ---
    generate_images: bool
    generate_campaign: bool
    generate_video: bool
    generate_podcast: bool

    # --- Export Formats ---
    export_formats: List[str]  # e.g., ["html", "pdf", "docx"]