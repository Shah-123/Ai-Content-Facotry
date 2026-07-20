# Expose nodes via modular agents package to maintain backwards compatibility
from .agents import (
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
    document_ingest_node,
    geval_evaluation_node,
    deepeval_evaluation_node,
)
from .agents.utils import _safe_slug
from .podcast_studio import podcast_node

__all__ = [
    "router_node",
    "research_node",
    "orchestrator_node",
    "fanout",
    "worker_node",
    "merge_content",
    "decide_images",
    "generate_and_place_images",
    "qa_agent_node",
    "revision_node",
    "campaign_generator_node",
    "video_generator_node",
    "document_ingest_node",
    "podcast_node",
    "geval_evaluation_node",
    "deepeval_evaluation_node",
    "_safe_slug"
]