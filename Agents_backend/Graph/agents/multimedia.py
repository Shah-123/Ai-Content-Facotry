import os
import re
import time
import random
import urllib.parse
import urllib.request
from typing import Optional
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State, GlobalImagePlan
from Graph.templates import DECIDE_IMAGES_SYSTEM
from .utils import logger, llm, _job, _emit, _safe_slug


def decide_images(state: State) -> dict:
    """
    Plans image placement based on the user's requested `num_images` count.
    If generate_images is False or num_images is 0, returns an empty image spec list.
    """
    generate_images = state.get("generate_images", True)
    num_images = state.get("num_images", 2)

    if not generate_images or num_images <= 0:
        logger.info("⏭️ Image generation disabled by user (num_images=0)")
        _emit(_job(state), "images", "completed", "Image generation skipped (user requested 0 images)", {"count": 0})
        return {"image_specs": []}

    _emit(_job(state), "images", "started", f"Planning {num_images} image placement(s)...")
    logger.info(f"🖼️ PLANNING {num_images} IMAGES ---")
    planner = llm.with_structured_output(GlobalImagePlan)

    custom_system_prompt = (
        f"{DECIDE_IMAGES_SYSTEM}\n\n"
        f"CRITICAL CONSTRAINT: You MUST plan EXACTLY {num_images} image(s) (no more, no less)."
    )

    image_plan = planner.invoke([
        SystemMessage(content=custom_system_prompt),
        HumanMessage(content=(
            f"Topic: {state.get('topic')}\n"
            f"Current Blog Content:\n{state.get('merged_md', '')}"
        )),
    ])

    specs = [img.model_dump() for img in image_plan.images[:num_images]]
    _emit(_job(state), "images", "working", f"Planned {len(specs)} image(s)", {"count": len(specs)})
    return {"image_specs": specs}


def _generate_image_openai_dalle(prompt: str, model: str | None = "dall-e-3", size: str | None = "1024x1024", quality: str | None = "standard", style: str | None = "vivid") -> Optional[bytes]:
    """Generates image using OpenAI DALL-E model with configured parameters."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = model or "dall-e-3"
    size = size or "1024x1024"
    quality = quality or "standard"
    style = style or "vivid"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        kwargs = {
            "model": model,
            "prompt": prompt[:1000],
            "n": 1,
            "size": size
        }
        if model == "dall-e-3":
            kwargs["quality"] = quality

        try:
            response = client.images.generate(**kwargs)
        except Exception as err:
            err_msg = str(err).lower()
            if "style" in err_msg or "quality" in err_msg or "unknown parameter" in err_msg:
                kwargs.pop("style", None)
                kwargs.pop("quality", None)
                response = client.images.generate(**kwargs)
            else:
                raise err
        if response.data and len(response.data) > 0:
            img_obj = response.data[0]
            if hasattr(img_obj, "b64_json") and img_obj.b64_json:
                import base64
                return base64.b64decode(img_obj.b64_json)
            if hasattr(img_obj, "url") and img_obj.url:
                req = urllib.request.Request(
                    img_obj.url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI Content Factory Engine"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read()
    except Exception as e:
        logger.warning(f"OpenAI image generation ({model}) failed: {e}")
    return None


def _generate_image_bytes_google(prompt: str) -> Optional[bytes]:
    """Generates image using Google GenAI (Gemini) with retries for rate limits."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)

        for attempt in range(3):
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
                    time.sleep(wait_time)
                    continue
                break
    except Exception as e:
        logger.warning(f"Google Gemini image generation skipped: {e}")
    return None


def _generate_image_pollinations(prompt: str) -> Optional[bytes]:
    """
    Fallback AI image generator using Pollinations.ai (Free, zero API key required).
    """
    try:
        encoded_prompt = urllib.parse.quote(prompt[:500])
        seed = random.randint(1000, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=600&model=flux&nologo=true&seed={seed}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI Content Factory Engine"}
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            if response.status == 200:
                return response.read()
    except Exception as e:
        logger.warning(f"Pollinations AI flux image generation failed: {e}")
    return None


def _generate_image_multi_provider(prompt: str, model: str | None = "dall-e-3", size: str | None = "1024x1024", quality: str | None = "standard", style: str | None = "vivid") -> Optional[bytes]:
    """
    Multi-provider AI image generation pipeline:
    1. Tries OpenAI DALL-E
    2. Tries Google Gemini / Imagen
    3. Falls back to Pollinations.ai (Free, zero API key needed)
    """
    model = model or "dall-e-3"
    size = size or "1024x1024"
    quality = quality or "standard"
    style = style or "vivid"

    # 1. OpenAI DALL-E
    image_bytes = _generate_image_openai_dalle(prompt, model=model, size=size, quality=quality, style=style)
    if image_bytes:
        logger.info(f"  🎨 Image generated via OpenAI {model}")
        return image_bytes

    # 2. Google Gemini
    image_bytes = _generate_image_bytes_google(prompt)
    if image_bytes:
        logger.info("  🎨 Image generated via Google Gemini")
        return image_bytes

    # 3. Pollinations AI (Zero API Key Fallback)
    image_bytes = _generate_image_pollinations(prompt)
    if image_bytes:
        logger.info("  🎨 Image generated via Pollinations AI (Free Zero-Key Engine)")
        return image_bytes

    return None


def generate_and_place_images(state: State) -> dict:
    """Generate images, save them, and insert portable Markdown into the article."""
    image_specs = state.get("image_specs", [])
    merged_md = state.get("merged_md", "")

    if not image_specs:
        logger.info("⏭️ No image specs to process")
        _emit(_job(state), "images", "completed", "No images requested")
        return {}

    _emit(_job(state), "images", "working", f"Generating {len(image_specs)} AI image(s)...")
    logger.info(f"🎨 GENERATING {len(image_specs)} AI IMAGES ---")

    base_path = state.get("blog_folder", ".")
    assets_path = f"{base_path}/assets/images"
    Path(assets_path).mkdir(parents=True, exist_ok=True)

    generated_count = 0
    updated_md = merged_md

    image_model = state.get("image_model") or "dall-e-3"
    image_size = state.get("image_size") or "1024x1024"
    image_quality = state.get("image_quality") or "standard"
    image_style = state.get("image_style") or "vivid"

    for idx, img in enumerate(image_specs):
        logger.info(f"Processing image {idx+1}/{len(image_specs)}: {img.get('filename')}")
        img_bytes = _generate_image_multi_provider(
            img["prompt"],
            model=image_model,
            size=image_size,
            quality=image_quality,
            style=image_style
        )

        if img_bytes:
            img_slug = _safe_slug(img.get("filename", f"image_{idx+1}"))
            if not img_slug.endswith(".png"):
                img_slug += ".png"
            if idx > 0:
                img_filename = f"{idx+1}_{img_slug}"
            else:
                img_filename = img_slug

            full_path = Path(f"{assets_path}/{img_filename}")
            full_path.write_bytes(img_bytes)
            generated_count += 1
            logger.info(f"✅ Saved AI image: {img_filename}")

            # Standard Markdown renders safely in the UI and remains portable in exports.
            alt_str = img.get("alt", "Blog Image").strip()
            alt_str = alt_str.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            caption_str = img.get("caption", "").strip()
            caption_markdown = (
                f"\n\n*{caption_str}*"
                if caption_str else ""
            )
            image_markdown = (
                f"\n\n![{alt_str}](assets/images/{img_filename})"
                f"{caption_markdown}\n\n"
            )

            # Insert image Markdown into updated_md.
            target = img.get("target_paragraph", "").strip()
            inserted = False
            if target and len(target) > 5 and target in updated_md:
                pos = updated_md.find(target)
                end_p = updated_md.find("\n\n", pos)
                if end_p != -1:
                    updated_md = updated_md[:end_p] + image_markdown + updated_md[end_p:]
                    inserted = True
                else:
                    updated_md += image_markdown
                    inserted = True

            if not inserted:
                if idx == 0:
                    # Hero image placement: insert right after H1 title line
                    first_nl = updated_md.find("\n\n")
                    if first_nl != -1:
                        updated_md = updated_md[:first_nl] + image_markdown + updated_md[first_nl:]
                    else:
                        updated_md += image_markdown
                else:
                    updated_md += image_markdown
        else:
            logger.error(f"❌ Failed image generation for spec: {img.get('filename')}")

    _emit(_job(state), "images", "completed", f"Generated {generated_count}/{len(image_specs)} images")

    if updated_md != merged_md:
        return {"merged_md": updated_md, "final": updated_md}
    return {}
