from pydantic import BaseModel, Field


class GenerationConfig(BaseModel):
    """Every user-controlled setting required to reproduce a generation job."""

    tone: str = "professional"
    audience: str = "general"
    sections: int = 3
    keywords: list[str] = Field(default_factory=list)
    generate_podcast: bool = False
    generate_video: bool = False
    generate_campaign: bool = False
    generate_qa: bool = True
    generate_images: bool = False
    num_images: int = 0
    upload_id: str | None = None
    source_mode: str = "hybrid"
    selected_model: str = "gpt-5-mini"
    image_model: str = "dall-e-3"
    image_size: str = "1024x1024"
    image_quality: str = "standard"
    image_style: str = "vivid"
    export_formats: list[str] = Field(default_factory=lambda: ["html"])
    # Experiment control only. False makes every worker receive the full
    # evidence pool instead of its assigned slice — the control arm for the
    # evidence-distribution ablation. Leave True for normal generation.
    assign_evidence: bool = True


class CreateJobRequest(GenerationConfig):
    topic: str


class RevisePlanRequest(BaseModel):
    feedback: str


class UpdatePlanRequest(BaseModel):
    """Accepts a directly-edited plan from the frontend outline editor."""

    blog_title: str
    tone: str = "professional"
    audience: str = "general"
    tasks: list[dict]
