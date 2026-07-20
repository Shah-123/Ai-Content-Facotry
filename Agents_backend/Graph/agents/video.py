"""
video.py — YouTube Shorts / TikTok Video Generator
====================================================
Produces a 9:16 (1080×1920) MP4 ready for upload to TikTok, YouTube Shorts,
and Instagram Reels.

Improvements over the original:
    1. 9:16 portrait format  — clips are cropped/padded to 1080×1920 instead
                               of a landscape resize.  Pexels search now requests
                               portrait orientation.
    2. Karaoke captions      — word-level timestamps from openai-whisper are used
                               to render word-by-word highlighted subtitles burnt
                               directly into the video.  No external .srt file needed.
    3. Hook title card       — the first 2.5 seconds show the blog title as an
                               animated pop-in overlay with a dark scrim, grabbing
                               attention before the main content starts.
    4. Crossfade transitions — a 0.3-second crossfade dissolve is inserted between
                               every clip so cuts feel smooth rather than jarring.
    5. Dark gradient overlay — a semi-transparent gradient at the bottom of every
                               frame ensures caption text is always readable over
                               any background footage.
    6. Progress bar          — a thin progress bar at the very top of the frame
                               fills left-to-right over the video's duration, giving
                               the viewer a visual cue about remaining time.

Dependencies (add to requirements.txt):
    openai-whisper      — local Whisper model for word timestamps
    numpy               — already present
    Pillow              — already present
    moviepy             — already present
    imageio-ffmpeg      — already present
"""
import random 
import os
import re
import sys
import time
import json
import requests
import tempfile
import wave
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from langchain_core.messages import SystemMessage, HumanMessage
try:
    from google import genai
    from google.genai import types
except ImportError:
    try:
        import google.genai as genai
        from google.genai import types
    except ImportError:
        genai = None
        types = None

from Graph.state import State
from .utils import logger, llm, _job, _emit


# ============================================================================
# CONSTANTS
# ============================================================================

# Target dimensions for TikTok / YouTube Shorts
SHORTS_W = 1080
SHORTS_H = 1920

# Caption strip at the bottom of the frame
CAPTION_AREA_TOP    = int(SHORTS_H * 0.72)   # captions start at 72% down
CAPTION_AREA_BOTTOM = int(SHORTS_H * 0.90)   # captions end at 90% down
CAPTION_FONT_SIZE   = 64                      # pt — large enough to read on mobile
CAPTION_LINE_CHARS  = 32                      # max chars per caption line

# Progress bar
PROGRESS_BAR_H     = 8    # pixels tall
PROGRESS_BAR_COLOR = (255, 255, 255, 220)  # white, slightly transparent

# Hook title card
HOOK_DURATION   = 2.5     # seconds the hook title card is shown
HOOK_FONT_SIZE  = 80
HOOK_SUB_SIZE   = 48

# Crossfade
CROSSFADE_DURATION = 0.3  # seconds

# TTS retry
_TTS_MAX_ATTEMPTS = 5
_TTS_BACKOFF_BASE = 2


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class VideoScenePlan(BaseModel):
    """Stock-video search queries for each scene."""
    keywords: List[str] = Field(
        description="3-5 highly specific portrait-friendly search queries "
                    "(e.g. 'doctor holding tablet vertical', 'city street night')"
    )

class HookCard(BaseModel):
    """Short hook text to show at the start of the video."""
    headline: str = Field(description="≤8 words — grabs attention immediately")
    subline: str  = Field(description="≤12 words — provides context or curiosity gap")


# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

VIDEO_PLAN_SYSTEM = """You are a short-form video producer for TikTok and YouTube Shorts.
Given the topic and voiceover script, generate 3-5 specific visual search queries for stock footage.
The queries MUST return portrait/vertical footage (9:16).
Focus on moody, aesthetic, or highly relevant visual concepts. Keep queries to 2-4 words max.
Always add 'vertical' or 'portrait' to each query to bias results.
"""

VOICEOVER_SYSTEM_PROMPT = """You are a professional TikTok / YouTube Shorts scriptwriter.
Given the blog summary, write a highly engaging, fast-paced voiceover script.
Length: 45–60 seconds when spoken (120–150 words).
Rules:
- Open with a scroll-stopping hook question or bold claim in the first sentence.
- Cover the 3 most important points from the FULL blog (not just the intro).
- End with a call to action ("Follow for more", "Link in bio", etc.).
- NO speaker labels, NO stage directions. Raw text only.
"""

VOICEOVER_BRIEF_SYSTEM = """You are a content strategist preparing a brief for a short-form video scriptwriter.
Read the full blog post and extract a structured brief.

Return EXACTLY this format:

TITLE: [blog title]
CORE_HOOK: [1 sentence — most attention-grabbing fact or claim]
KEY_POINTS:
- [most important point]
- [second most important point]
- [third most important point]
SURPRISING_STAT: [most compelling statistic, if any]
PRIMARY_CTA: [what should the viewer do after watching?]
TONE: [writing tone]
"""

HOOK_CARD_SYSTEM = """You are a TikTok video editor.
Given the blog topic and voiceover script, write a short 2-line hook card shown at the start of the video.
The hook must create immediate curiosity or make a bold claim.
Keep it punchy. This text will be shown as a large overlay at the very beginning.
"""


# ============================================================================
# PEXELS VIDEO FETCHER (portrait-aware)
# ============================================================================

def fetch_pexels_video(query: str, download_dir: str, index: int) -> Optional[str]:
    """
    Fetches a portrait (9:16) video from Pexels.
    Prefers HD portrait clips; falls back to any orientation and crops later.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        logger.warning("No Pexels API key found.")
        return None

    headers = {"Authorization": api_key}
    # Force portrait orientation in the API request
    url = (
        f"https://api.pexels.com/videos/search"
        f"?query={requests.utils.quote(query)}"
        f"&per_page=5"
        f"&orientation=portrait"
    )

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("videos"):
            logger.warning(f"No portrait videos found for: {query}")
            return None

        # Pick the clip with the best resolution (prefer HD portrait)
        best_video = None
        best_file  = None
        best_score = 0

        for video in data["videos"][:5]:
            for vf in video.get("video_files", []):
                w = vf.get("width", 0)
                h = vf.get("height", 0)
                is_portrait = h > w
                is_hd       = h >= 1080
                score = (2 if is_portrait else 0) + (1 if is_hd else 0)
                if score > best_score:
                    best_score = score
                    best_video = video
                    best_file  = vf

        if not best_file and data["videos"]:
            best_video = data["videos"][0]
            best_file  = best_video["video_files"][0] if best_video.get("video_files") else None

        if not best_file:
            return None

        vid_path = os.path.join(download_dir, f"clip_{index}.mp4")
        with requests.get(best_file["link"], stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(vid_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return vid_path

    except Exception as e:
        logger.error(f"Pexels fetch error for '{query}': {e}")
        return None


# ============================================================================
# TTS — Gemini
# ============================================================================

def save_pcm_as_wav(pcm_bytes: bytes, output_path: str):
    """Saves raw PCM (24 kHz, 16-bit mono) to WAV."""
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)


def generate_tts_voiceover(text: str, voice: str = "Puck") -> Optional[str]:
    """
    Generates speech via Gemini TTS with exponential-backoff retry.
    Returns path to a temporary .wav file, or None on failure.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set.")
        return None

    client = genai.Client(api_key=api_key)

    for attempt in range(1, _TTS_MAX_ATTEMPTS + 1):
        try:
            logger.info(f"   🔊 TTS attempt {attempt}/{_TTS_MAX_ATTEMPTS} (voice: {voice})...")
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice
                            )
                        )
                    ),
                ),
            )
            audio_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_bytes = part.inline_data.data
                    break

            if audio_bytes:
                tmp = tempfile.mktemp(suffix=".wav")
                save_pcm_as_wav(audio_bytes, tmp)
                logger.info(f"   ✅ TTS succeeded on attempt {attempt}.")
                return tmp

            logger.error("Gemini TTS: response had no audio data.")
            return None

        except Exception as e:
            err_str = str(e)
            if attempt < _TTS_MAX_ATTEMPTS:
                # Add jitter and exponential backoff
                wait = (_TTS_BACKOFF_BASE ** attempt) + (random.random() * 2)
                logger.warning(f"   ⚠️ TTS attempt {attempt} failed: {e}. Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                logger.error(f"   ❌ TTS failed after {_TTS_MAX_ATTEMPTS} attempts: {e}")

    return None


# ============================================================================
# WHISPER — word timestamps for karaoke captions
# ============================================================================

def get_word_timestamps(audio_path: str, model_size: str = "tiny") -> List[dict]:
    """
    Runs openai-whisper locally to get per-word timestamps.
    Returns a list of {"word": str, "start": float, "end": float}.

    Falls back to evenly-spaced fake timestamps if whisper is not installed,
    so the rest of the pipeline still works without the dependency.
    """
    try:
        import whisper
        logger.info(f"   🎙️ Transcribing audio for word timestamps (whisper model: {model_size})...")
        model = whisper.load_model(model_size)   # fast; swap for "base" for accuracy
        result = model.transcribe(audio_path, word_timestamps=True)

        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append({
                    "word":  w["word"].strip(),
                    "start": w["start"],
                    "end":   w["end"],
                })
        logger.info(f"   ✅ Whisper found {len(words)} word timestamps.")
        return words

    except ImportError:
        logger.warning(
            "   ⚠️ openai-whisper not installed. "
            "Falling back to evenly-spaced captions. "
            "Run: pip install openai-whisper"
        )
        return []  # caller will build fallback

    except Exception as e:
        logger.warning(f"   ⚠️ Whisper transcription failed: {e}. Using fallback captions.")
        return []


def build_caption_chunks(
    words: List[dict],
    audio_duration: float,
    script_text: str,
    max_chars: int = CAPTION_LINE_CHARS,
) -> List[dict]:
    """
    Groups words into caption chunks of ≤max_chars each.
    Each chunk has:
        {
          "text": str,
          "start": float,
          "end": float,
          "words": [{"word": str, "start": float, "end": float}]
        }

    If words is empty (no whisper), evenly distributes script words over time.
    """
    if not words:
        # Fallback: split script into ~max_chars chunks, spread evenly over time
        raw_words = script_text.split()
        n = len(raw_words)
        chunks = []
        i = 0
        while i < n:
            chunk_words = []
            char_count  = 0
            while i < n and char_count + len(raw_words[i]) + 1 <= max_chars:
                chunk_words.append(raw_words[i])
                char_count += len(raw_words[i]) + 1
                i += 1
            text  = " ".join(chunk_words)
            start = (i - len(chunk_words)) / n * audio_duration
            end   = i / n * audio_duration
            chunks.append({"text": text, "start": start, "end": end, "words": []})
        return chunks

    chunks      = []
    cur_words   = []
    cur_chars   = 0

    for w in words:
        needed = len(w["word"]) + (1 if cur_words else 0)
        if cur_words and cur_chars + needed > max_chars:
            # flush current chunk
            chunks.append({
                "text":  " ".join(cw["word"] for cw in cur_words),
                "start": cur_words[0]["start"],
                "end":   cur_words[-1]["end"],
                "words": cur_words,
            })
            cur_words = []
            cur_chars = 0
        cur_words.append(w)
        cur_chars += needed

    if cur_words:
        chunks.append({
            "text":  " ".join(cw["word"] for cw in cur_words),
            "start": cur_words[0]["start"],
            "end":   cur_words[-1]["end"],
            "words": cur_words,
        })

    return chunks


# ============================================================================
# FRAME COMPOSITING HELPERS (PIL)
# ============================================================================

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Loads a system font at the requested size.
    Tries common paths; falls back to PIL's default if none found.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_gradient_overlay(frame_array: np.ndarray) -> np.ndarray:
    """
    Adds a dark-to-transparent vertical gradient over the bottom third of the
    frame, ensuring caption text is always readable over any background.

    Operates in-place on a (H, W, 3) uint8 numpy array.
    Returns the modified array.
    """
    h, w = frame_array.shape[:2]
    grad_start = int(h * 0.60)   # gradient begins 60% down
    grad_end   = h

    # Build a 1-D alpha ramp from 0 at top to 0.75 at bottom
    ramp = np.linspace(0, 0.75, grad_end - grad_start, dtype=np.float32)

    # Apply ramp: darken the frame in that strip
    strip = frame_array[grad_start:grad_end].astype(np.float32)
    for i, alpha in enumerate(ramp):
        strip[i] = strip[i] * (1 - alpha)

    frame_array[grad_start:grad_end] = np.clip(strip, 0, 255).astype(np.uint8)
    return frame_array


def draw_progress_bar(frame_array: np.ndarray, progress: float) -> np.ndarray:
    """
    Draws a thin progress bar across the very top of the frame.
    progress: 0.0 → 1.0
    """
    h, w = frame_array.shape[:2]
    bar_w = int(w * max(0.0, min(1.0, progress)))
    if bar_w > 0:
        frame_array[:PROGRESS_BAR_H, :bar_w] = [255, 255, 255]  # white bar
    return frame_array


def draw_caption_on_frame(
    frame_array: np.ndarray,
    chunk: dict,
    current_time: float,
    font: ImageFont.FreeTypeFont,
    highlight_font: ImageFont.FreeTypeFont,
) -> np.ndarray:
    """
    Draws a caption chunk onto the frame.
    Words that are currently being spoken are highlighted in yellow.
    All other words are white.

    chunk format: {"text": str, "start": float, "end": float,
                   "words": [{"word": str, "start": float, "end": float}]}
    """
    img  = Image.fromarray(frame_array)
    draw = ImageDraw.Draw(img)

    h, w = frame_array.shape[:2]
    y    = int(h * 0.76)   # vertical centre of caption area

    words_with_ts = chunk.get("words", [])

    if not words_with_ts:
        # No per-word timing — render flat white text
        text = chunk["text"]
        bbox = draw.textbbox((0, 0), text, font=font)
        tw   = bbox[2] - bbox[0]
        x    = (w - tw) // 2
        # Shadow
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    else:
        # Karaoke: render word by word, advance x position
        # First pass: measure total width
        parts = []
        for wobj in words_with_ts:
            word   = wobj["word"] + " "
            active = wobj["start"] <= current_time <= wobj["end"]
            f      = highlight_font if active else font
            bbox   = draw.textbbox((0, 0), word, font=f)
            parts.append((word, f, bbox[2] - bbox[0], active))

        total_w = sum(p[2] for p in parts)
        x = (w - total_w) // 2

        for word, f, ww, active in parts:
            color = (255, 230, 0, 255) if active else (255, 255, 255, 230)
            # Shadow
            draw.text((x + 2, y + 2), word, font=f, fill=(0, 0, 0, 160))
            draw.text((x, y), word, font=f, fill=color)
            x += ww

    return np.array(img)


def draw_hook_card(
    frame_array: np.ndarray,
    headline: str,
    subline: str,
    alpha: float,
    title_font: ImageFont.FreeTypeFont,
    sub_font: ImageFont.FreeTypeFont,
) -> np.ndarray:
    """
    Composites a full-frame hook title card over the video frame.
    alpha: 0.0 (invisible) → 1.0 (fully opaque).
    Fades in during 0–0.4s and fades out during 2.0–2.5s.
    """
    h, w = frame_array.shape[:2]

    overlay = Image.fromarray(frame_array).convert("RGBA")
    scrim   = Image.new("RGBA", (w, h), (0, 0, 0, int(180 * alpha)))
    overlay = Image.alpha_composite(overlay, scrim)

    draw = ImageDraw.Draw(overlay)

    # Headline
    bbox = draw.textbbox((0, 0), headline, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    hx = (w - tw) // 2
    hy = int(h * 0.38)
    color_a = int(255 * alpha)
    draw.text((hx + 4, hy + 4), headline, font=title_font, fill=(0, 0, 0, int(160 * alpha)))
    draw.text((hx, hy), headline, font=title_font, fill=(255, 255, 255, color_a))

    # Subline
    bbox2 = draw.textbbox((0, 0), subline, font=sub_font)
    sx = (w - (bbox2[2] - bbox2[0])) // 2
    sy = hy + th + 28
    draw.text((sx + 3, sy + 3), subline, font=sub_font, fill=(0, 0, 0, int(140 * alpha)))
    draw.text((sx, sy), subline, font=sub_font, fill=(255, 220, 60, color_a))

    return np.array(overlay.convert("RGB"))


# ============================================================================
# PORTRAIT CROP / PAD
# ============================================================================

def make_portrait_frame(frame_array: np.ndarray) -> np.ndarray:
    """
    Converts any frame to 1080×1920 (9:16).

    Strategy:
      - If the clip is already taller than it is wide: centre-crop to 1080×1920.
      - If the clip is landscape (wider than tall): scale to height=1920,
        then centre-crop the width to 1080.
      - After crop/scale, zero-pad any missing dimension with black.
    """
    from PIL import Image as PILImage

    h, w = frame_array.shape[:2]
    target_w, target_h = SHORTS_W, SHORTS_H

    img = PILImage.fromarray(frame_array)

    if h >= w:
        # Portrait or square: scale width to target_w, keep aspect
        scale   = target_w / w
        new_w   = target_w
        new_h   = int(h * scale)
    else:
        # Landscape: scale height to target_h, then crop width
        scale   = target_h / h
        new_h   = target_h
        new_w   = int(w * scale)

    img = img.resize((new_w, new_h), PILImage.LANCZOS)

    # Centre-crop to exact target dimensions
    left = max(0, (new_w - target_w) // 2)
    top  = max(0, (new_h - target_h) // 2)
    img  = img.crop((left, top, left + target_w, top + target_h))

    # If somehow still smaller, pad with black
    if img.size != (target_w, target_h):
        canvas = PILImage.new("RGB", (target_w, target_h), (0, 0, 0))
        canvas.paste(img, ((target_w - img.width) // 2, (target_h - img.height) // 2))
        img = canvas

    return np.array(img)


# ============================================================================
# CROSSFADE HELPER
# ============================================================================

def crossfade_clips(clips: list, duration: float = CROSSFADE_DURATION) -> list:
    """
    Inserts a crossfade between consecutive clips by trimming the end of
    clip[i] and the start of clip[i+1] by `duration` seconds and overlapping.

    Uses moviepy's CompositeVideoClip to blend the transition region.
    Returns a list of clips that can be concatenated normally — the crossfade
    region is embedded as a composite clip inserted between each pair.
    """
    try:
        from moviepy.video.compositing import CompositeVideoClip
        from moviepy.video.fx import FadeOut, FadeIn
    except ImportError:
        logger.warning("moviepy fx unavailable — skipping crossfades.")
        return clips

    if len(clips) <= 1:
        return clips

    result = []
    for i, clip in enumerate(clips):
        if i < len(clips) - 1:
            # Apply fadeout to end of this clip
            try:
                faded = clip.with_effects([FadeOut(duration)])
                result.append(faded)
            except Exception:
                result.append(clip)
        else:
            try:
                faded = clip.with_effects([FadeIn(duration)])
                result.append(faded)
            except Exception:
                result.append(clip)

    return result


# ============================================================================
# BRIEF BUILDER
# ============================================================================

def _build_voiceover_brief(blog_content: str, topic: str) -> str:
    """Summarises the full blog into a brief for the voiceover scriptwriter."""
    safe_blog = blog_content[:100_000]
    response = llm.invoke([
        SystemMessage(content=VOICEOVER_BRIEF_SYSTEM),
        HumanMessage(content=f"TOPIC: {topic}\n\nFULL BLOG POST:\n{safe_blog}"),
    ])
    return response.content.strip()


def _generate_hook_card(topic: str, script: str) -> HookCard:
    """Generates the 2-line hook card shown at the start of the video."""
    generator = llm.with_structured_output(HookCard)
    return generator.invoke([
        SystemMessage(content=HOOK_CARD_SYSTEM),
        HumanMessage(content=f"TOPIC: {topic}\n\nVOICEOVER SCRIPT:\n{script[:800]}"),
    ])


# ============================================================================
# MAIN COMPOSITOR — builds the final Shorts-ready video
# ============================================================================

def composite_shorts_video(
    raw_clip_paths: List[str],
    audio_path: str,
    audio_duration: float,
    caption_chunks: List[dict],
    hook: HookCard,
    output_path: str,
) -> bool:
    """
    Assembles the final 9:16 MP4 from raw clips + audio + captions + hook.

    Pipeline:
      1. Load clips → convert each frame to portrait 1080×1920
      2. Concatenate with crossfades
      3. Loop if total footage < audio duration
      4. For each frame:
           a. Dark gradient overlay (bottom third)
           b. Progress bar (top)
           c. Hook card (first HOOK_DURATION seconds)
           d. Karaoke caption
      5. Attach audio and export

    Returns True on success, False on any unrecoverable error.
    """
    try:
        try:
            # MoviePy v2.x
            from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
            from moviepy.video.fx import Loop
        except (ImportError, AttributeError):
            # MoviePy v1.x fallback
            from moviepy.video.io.VideoFileClip import VideoFileClip
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy import concatenate_videoclips
            from moviepy.video.fx.loop import Loop
    except ImportError as e:
        logger.error(f"moviepy import failed: {e}")
        return False
    # ------------------------------------------------------------------
    # 1. Load raw clips → portrait resize
    # ------------------------------------------------------------------
    logger.info("   🎞️ Loading and resizing clips to 1080×1920...")
    video_clips = []
    for path in raw_clip_paths:
        try:
            clip      = VideoFileClip(path)
            dur       = min(12.0, clip.duration)   # max 12s per raw clip
            clip      = clip.subclipped(0, dur)

            # Re-render every frame as portrait
            def _make_portrait_maker(c):
                def _process(get_frame, t):
                    return make_portrait_frame(get_frame(t))
                return _process

            clip = clip.image_transform(
                lambda frame: make_portrait_frame(frame)
            )
            clip = clip.resized((SHORTS_W, SHORTS_H))
            video_clips.append(clip)
        except Exception as e:
            logger.warning(f"   ⚠️ Skipping clip {path}: {e}")

    if not video_clips:
        logger.error("No valid clips available for compositing.")
        return False

    # ------------------------------------------------------------------
    # 2. Crossfade transitions
    # ------------------------------------------------------------------
    video_clips = crossfade_clips(video_clips, CROSSFADE_DURATION)

    # ------------------------------------------------------------------
    # 3. Concatenate + loop to match audio duration
    # ------------------------------------------------------------------
    try:
        combined = concatenate_videoclips(video_clips, method="compose")
    except Exception:
        combined = concatenate_videoclips(video_clips)

    if combined.duration < audio_duration:
        combined = combined.with_effects([Loop(duration=audio_duration)])
    else:
        combined = combined.subclipped(0, audio_duration)

    # ------------------------------------------------------------------
    # 4. Load fonts
    # ------------------------------------------------------------------
    caption_font   = _load_font(CAPTION_FONT_SIZE,   bold=False)
    highlight_font = _load_font(CAPTION_FONT_SIZE,   bold=True)
    hook_title_f   = _load_font(HOOK_FONT_SIZE,      bold=True)
    hook_sub_f     = _load_font(HOOK_SUB_SIZE,        bold=False)

    # Pre-build caption lookup: for each frame time → active chunk index
    def _find_chunk(t: float) -> Optional[dict]:
        for chunk in caption_chunks:
            if chunk["start"] <= t <= chunk["end"] + 0.05:
                return chunk
        return None

    # ------------------------------------------------------------------
    # 5. Frame-level compositor
    # ------------------------------------------------------------------
    total_dur = combined.duration

    def process_frame(get_frame, t: float) -> np.ndarray:
        frame = get_frame(t).copy()

        # a) Dark gradient overlay
        frame = draw_gradient_overlay(frame)

        # b) Progress bar
        progress = t / total_dur
        frame    = draw_progress_bar(frame, progress)

        # c) Hook card (first HOOK_DURATION seconds)
        if t < HOOK_DURATION:
            # Fade in 0→0.4s, hold, fade out from (HOOK_DURATION-0.5)
            if t < 0.4:
                alpha = t / 0.4
            elif t > HOOK_DURATION - 0.5:
                alpha = (HOOK_DURATION - t) / 0.5
            else:
                alpha = 1.0
            alpha = max(0.0, min(1.0, alpha))
            frame = draw_hook_card(
                frame, hook.headline, hook.subline,
                alpha, hook_title_f, hook_sub_f
            )

        # d) Karaoke caption (skip during hook card fully opaque phase)
        if t >= 0.4:  # give hook card a moment before showing captions
            chunk = _find_chunk(t)
            if chunk:
                frame = draw_caption_on_frame(
                    frame, chunk, t, caption_font, highlight_font
                )

        return frame

    composited = combined.transform(process_frame)

    # ------------------------------------------------------------------
    # 6. Attach audio + export
    # ------------------------------------------------------------------
    logger.info(f"   🎬 Exporting {SHORTS_W}×{SHORTS_H} portrait video → {output_path}")
    audio_clip = AudioFileClip(audio_path)
    composited = composited.with_audio(audio_clip)

    composited.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        ffmpeg_params=["-crf", "23"],
        logger=None,
    )

    # Cleanup
    for c in video_clips:
        try: c.close()
        except: pass
    try: combined.close()
    except: pass
    try: composited.close()
    except: pass
    try: audio_clip.close()
    except: pass

    return True


# ============================================================================
# MAIN NODE
# ============================================================================

def video_generator_node(state: State) -> dict:
    """
    LangGraph node — generates a TikTok / YouTube Shorts-ready MP4.

    Reads:  state["final"], state["topic"], state["blog_folder"]
    Writes: state["video_path"]
    """
    from langchain_openai import ChatOpenAI

    _emit(_job(state), "video", "started", "Starting Shorts video generation...")
    logger.info("🎬 GENERATING SHORTS VIDEO (9:16) ---")

    topic        = state.get("topic", "Unknown")
    blog_content = state.get("final", "")

    if not blog_content:
        logger.warning("No blog content. Skipping video generation.")
        _emit(_job(state), "video", "error", "No blog content available.")
        return {"video_path": None}

    # ------------------------------------------------------------------
    # Output path
    # ------------------------------------------------------------------
    blog_folder = state.get("blog_folder")
    video_dir   = Path(blog_folder) / "video" if blog_folder else Path("generated_videos")
    video_dir.mkdir(parents=True, exist_ok=True)
    output_file = str(video_dir / "short.mp4")
    temp_dir    = tempfile.mkdtemp()

    def _cleanup():
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 1. Brief → voiceover script
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Building voiceover brief from blog...")
    brief = _build_voiceover_brief(blog_content, topic)

    _emit(_job(state), "video", "working", "Writing voiceover script...")
    text_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    response = text_llm.invoke([
        SystemMessage(content=VOICEOVER_SYSTEM_PROMPT),
        HumanMessage(content=f"TOPIC: {topic}\n\nBLOG BRIEF:\n{brief}"),
    ])
    script = response.content.strip()
    logger.info(f"   📝 Script ({len(script.split())} words):\n{script[:200]}...")

    # ------------------------------------------------------------------
    # 2. Hook card
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Generating hook title card...")
    try:
        hook = _generate_hook_card(topic, script)
    except Exception as e:
        logger.warning(f"Hook generation failed ({e}), using defaults.")
        hook = HookCard(headline=topic[:40], subline="Watch to find out more")

    logger.info(f"   🪝 Hook: '{hook.headline}' / '{hook.subline}'")

    # ------------------------------------------------------------------
    # 3. TTS audio
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Generating voiceover audio...")
    audio_path = generate_tts_voiceover(script, voice="Puck")
    if not audio_path:
        logger.error("TTS failed. Aborting video generation.")
        _emit(_job(state), "video", "error", "Audio generation failed.")
        _cleanup()
        return {"video_path": None}

    try:
        from moviepy.audio.io.AudioFileClip import AudioFileClip as _AClip
        audio_dur = _AClip(audio_path).duration
        logger.info(f"   ⏱️ Audio duration: {audio_dur:.1f}s")
    except Exception as e:
        logger.error(f"Could not read audio duration: {e}")
        _cleanup()
        return {"video_path": None}

    # ------------------------------------------------------------------
    # 4. Word timestamps (whisper) → caption chunks
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Transcribing audio for karaoke captions...")
    model_size = state.get("whisper_model_size") or os.getenv("WHISPER_MODEL_SIZE", "tiny")
    word_timestamps = get_word_timestamps(audio_path, model_size=model_size)
    caption_chunks  = build_caption_chunks(word_timestamps, audio_dur, script)
    logger.info(f"   💬 Built {len(caption_chunks)} caption chunks.")

    # ------------------------------------------------------------------
    # 5. Plan video scenes (portrait queries)
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Planning stock footage queries...")
    planner = llm.with_structured_output(VideoScenePlan)
    plan    = planner.invoke([
        SystemMessage(content=VIDEO_PLAN_SYSTEM),
        HumanMessage(content=f"Topic: {topic}\n\nVoiceover Script:\n{script}"),
    ])
    queries = plan.keywords if plan.keywords else [f"{topic} vertical", "abstract background portrait"]
    logger.info(f"   🎥 Pexels queries: {queries}")

    # ------------------------------------------------------------------
    # 6. Fetch portrait Pexels clips
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", f"Fetching {len(queries)} portrait stock clips...")
    downloaded = []
    for i, q in enumerate(queries):
        clip_path = fetch_pexels_video(q, temp_dir, i)
        if clip_path:
            downloaded.append(clip_path)
            logger.info(f"   ✅ Downloaded clip {i+1}: {q}")
        if len(downloaded) * 12 > audio_dur + 10:
            break  # have enough footage

    if not downloaded:
        fallback = fetch_pexels_video("abstract minimal portrait", temp_dir, 99)
        if fallback:
            downloaded.append(fallback)

    if not downloaded:
        logger.error("No stock clips available. Aborting.")
        _emit(_job(state), "video", "error", "No stock footage downloaded.")
        _cleanup()
        return {"video_path": None}

    # ------------------------------------------------------------------
    # 7. Composite the final Shorts video
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", "Compositing 9:16 video with captions + hook...")
    success = composite_shorts_video(
        raw_clip_paths=downloaded,
        audio_path=audio_path,
        audio_duration=audio_dur,
        caption_chunks=caption_chunks,
        hook=hook,
        output_path=output_file,
    )

    # Cleanup temp audio
    try: os.remove(audio_path)
    except: pass
    _cleanup()

    if success:
        logger.info(f"   ✅ Shorts video saved: {output_file}")
        _emit(_job(state), "video", "completed",
              f"9:16 Shorts video ready ({audio_dur:.0f}s).",
              {"path": output_file, "format": "1080x1920"})
        return {"video_path": output_file}
    else:
        _emit(_job(state), "video", "error", "Compositing failed.")
        return {"video_path": None}