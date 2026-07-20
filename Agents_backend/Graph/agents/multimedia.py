import os
import re
import time
import random
from typing import Optional
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State, GlobalImagePlan
from Graph.templates import DECIDE_IMAGES_SYSTEM
from .utils import logger, llm, _job, _emit, _safe_slug

def decide_images(state: State) -> dict:
    _emit(_job(state), "images", "started", "Planning image placement...")
    logger.info("🖼️ PLANNING IMAGES ---")
    planner = llm.with_structured_output(GlobalImagePlan)
    
    image_plan = planner.invoke([
        SystemMessage(content=DECIDE_IMAGES_SYSTEM),
        HumanMessage(content=(
            f"Topic: {state['topic']}\n"
            f"Current Blog Content:\n{state['merged_md']}" 
        )),
    ])

    _emit(_job(state), "images", "working", f"Planned {len(image_plan.images)} images", {"count": len(image_plan.images)})
    return {
        "image_specs": [img.model_dump() for img in image_plan.images],
    }

def _generate_image_bytes_google(prompt: str) -> Optional[bytes]:
    """Generates image using Google GenAI (Gemini) with retries for rate limits."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        try:
            import google.genai as genai
            from google.genai import types
        except ImportError:
            logger.warning("Google GenAI library not found or fails to import.")
            return None
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: 
        logger.warning("GOOGLE_API_KEY not found for image generation.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        
        for attempt in range(5): # Up to 5 attempts
            try:
                resp = client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
                )
                
                if resp.candidates and resp.candidates[0].content.parts:
                    for part in resp.candidates[0].content.parts:
                        if part.inline_data:
                            return part.inline_data.data
                return None
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"⚠️ Gemini rate limited (429). Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/5)")
                    time.sleep(wait_time)
                    continue
                raise e # Re-raise other exceptions to be caught by outer try
            
    except Exception as e:
        logger.error(f"❌ Image generation failed: {e}")
        return None

def generate_and_place_images(state: State) -> dict:
    """Generates images and saves them to the assets folder without modifying the blog text."""
    _emit(_job(state), "images", "working", "Generating AI images...")
    logger.info("🎨 GENERATING IMAGES & SAVING ---")
    
    image_specs = state.get("image_specs", [])
    base_path = state.get("blog_folder", ".")
    assets_path = f"{base_path}/assets/images"
    
    if os.getenv("GOOGLE_API_KEY") and image_specs:
        logger.info(f"Attempting to generate {len(image_specs)} images...")
        
        Path(assets_path).mkdir(parents=True, exist_ok=True)

        for img in image_specs:
            img_bytes = _generate_image_bytes_google(img["prompt"])
            
            if img_bytes:
                img_filename = _safe_slug(img["filename"])
                if not img_filename.endswith(".png"): img_filename += ".png"
                
                full_path = Path(f"{assets_path}/{img_filename}")
                full_path.write_bytes(img_bytes)
                logger.info(f"✅ Generated: {img_filename}")
            else:
                logger.error(f"Failed: {img['filename']} (skipping)")
                
    else:
        logger.info("⏭️ Skipped Image Generation (No API Key or no specs)")

    _emit(_job(state), "images", "completed", "Images processed")
    
    # We do NOT return "final" anymore because we aren't modifying the markdown inline.
    return {}
