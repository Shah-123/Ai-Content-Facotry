from pydantic import BaseModel

class CreateJobRequest(BaseModel):
    topic: str
    tone: str = "professional"
    audience: str = "general"
    sections: int = 3
    # SEO keywords the writer should weave into the blog. Empty list skips
    # keyword optimization. The frontend passes a comma-split list.
    keywords: list[str] = []
    generate_podcast: bool = False
    generate_video: bool = False
    generate_campaign: bool = False
    generate_qa: bool = True
    # — Document upload (optional) —
    upload_id: str | None = None
    source_mode: str = "hybrid"   # "closed_book" | "hybrid" | "auto_topic"


class RevisePlanRequest(BaseModel):
    feedback: str


class UpdatePlanRequest(BaseModel):
    """Accepts a directly-edited plan from the frontend outline editor."""
    blog_title: str
    tone: str = "professional"
    audience: str = "general"
    tasks: list[dict]  # Each dict has: title, goal, bullets, target_words, tags
