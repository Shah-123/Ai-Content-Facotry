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
    4. Dark gradient overlay — a semi-transparent gradient at the bottom of every
                               frame ensures caption text is always readable over
                               any background footage.
    5. Progress bar          — a thin progress bar at the very top of the frame
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
import shutil
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import numpy as np
from proglog import ProgressBarLogger
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State
from .utils import logger, llm, _job, _emit, _REQUEST_TIMEOUT


# ============================================================================
# CONSTANTS
# ============================================================================

# Target dimensions for TikTok / YouTube Shorts
SHORTS_W = 1080
SHORTS_H = 1920
SHORTS_FPS = 30

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

        # Smallest portrait file that still covers the 1920px output height.
        # The old "first HD portrait file" rule usually landed on a 1440×2560 or
        # 2160×3840 UHD file, which is several times the download and decode
        # for a frame that gets scaled down to 1080×1920 anyway.
        best_file = None
        for video in data["videos"][:5]:
            fits = [vf for vf in video.get("video_files", [])
                    if vf.get("height", 0) > vf.get("width", 0)
                    and vf.get("height", 0) >= SHORTS_H]
            if fits:
                best_file = min(fits, key=lambda vf: vf["height"])
                break

        if not best_file:
            # Nothing tall enough — take the tallest file on offer and upscale.
            files = [vf for v in data["videos"][:5] for vf in v.get("video_files", [])]
            best_file = max(files, key=lambda vf: vf.get("height", 0), default=None)

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


def create_synthetic_background_clip(duration: float, output_path: str) -> Optional[str]:
    """
    Generates a dark ambient gradient MP4 clip (1080x1920) as a fallback
    when Pexels API key is missing or stock clip downloads fail.
    """
    try:
        try:
            from moviepy import VideoClip
        except (ImportError, AttributeError):
            from moviepy.video.VideoClip import VideoClip
    except ImportError:
        logger.error("MoviePy VideoClip import failed for synthetic background.")
        return None

    def make_frame(t):
        w, h = SHORTS_W, SHORTS_H
        y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        phase = (t / max(duration, 1.0)) * 2 * np.pi
        
        r = (22 + 12 * np.sin(phase) + y * 8).astype(np.uint8)
        g = (18 + 14 * np.cos(phase) + y * 18).astype(np.uint8)
        b = (48 + 24 * np.sin(phase + np.pi / 2) + y * 42).astype(np.uint8)

        frame = np.dstack([
            np.broadcast_to(r, (h, w)),
            np.broadcast_to(g, (h, w)),
            np.broadcast_to(b, (h, w))
        ])
        return frame

    try:
        clip = VideoClip(make_frame, duration=duration)
        clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            preset="ultrafast",
            logger=None
        )
        clip.close()
        return output_path
    except Exception as e:
        logger.error(f"Failed to create synthetic background clip: {e}")
        return None


# ============================================================================
# TTS — OpenAI
# ============================================================================

def save_pcm_as_wav(pcm_bytes: bytes, output_path: str):
    """Saves raw PCM (24 kHz, 16-bit mono) to WAV."""
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)


def generate_tts_voiceover(text: str, voice: str = "nova") -> Optional[str]:
    """
    Generates speech via OpenAI TTS (tts-1-hd, as the podcast uses) with
    exponential-backoff retry. Returns path to a temporary .wav file, or None.
    """
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set.")
        return None

    from openai import OpenAI
    # The loop below owns retries and backoff, so the SDK's own are off.
    client = OpenAI(timeout=_REQUEST_TIMEOUT, max_retries=0)

    for attempt in range(1, _TTS_MAX_ATTEMPTS + 1):
        try:
            logger.info(f"   🔊 TTS attempt {attempt}/{_TTS_MAX_ATTEMPTS} (voice: {voice})...")
            response = client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=text,
                response_format="pcm",  # 24 kHz, 16-bit mono — what save_pcm_as_wav writes
            )
            if response.content:
                fd, tmp = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                save_pcm_as_wav(response.content, tmp)
                logger.info(f"   ✅ TTS succeeded on attempt {attempt}.")
                return tmp

            logger.error("OpenAI TTS: response had no audio data.")
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
    Transcribes audio using OpenAI's API to get per-word timestamps.
    Falls back to local whisper or evenly-spaced fake timestamps if API fails or key is missing.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            logger.info("   🎙️ Transcribing audio via OpenAI Whisper API for word timestamps...")
            client = OpenAI(api_key=api_key)
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            words = []
            # Check for words in verbose_json response model or dictionary
            if hasattr(response, "words") and response.words:
                for w in response.words:
                    w_dict = w if isinstance(w, dict) else getattr(w, "__dict__", w)
                    words.append({
                        "word": w_dict.get("word", "").strip(),
                        "start": float(w_dict.get("start", 0.0)),
                        "end": float(w_dict.get("end", 0.0)),
                    })
            elif isinstance(response, dict) and "words" in response:
                for w in response["words"]:
                    words.append({
                        "word": w.get("word", "").strip(),
                        "start": float(w.get("start", 0.0)),
                        "end": float(w.get("end", 0.0)),
                    })
            
            if words:
                logger.info(f"   ✅ OpenAI API found {len(words)} word timestamps.")
                return words
        except Exception as api_err:
            logger.warning(f"   ⚠️ OpenAI API Whisper transcription failed: {api_err}. Trying local fallback...")

    # Local fallback
    try:
        import whisper
        logger.info(f"   🎙️ Local Fallback: Transcribing audio (whisper model: {model_size})...")
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
        logger.info(f"   ✅ Local Whisper found {len(words)} word timestamps.")
        return words

    except ImportError:
        logger.warning(
            "   ⚠️ openai-whisper not installed. "
            "Falling back to evenly-spaced captions."
        )
        return []  # caller will build fallback

    except Exception as e:
        logger.warning(f"   ⚠️ Local Whisper transcription failed: {e}. Using fallback captions.")
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
# FRAME COMPOSITING HELPERS (PIL images, overlaid by ffmpeg)
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

    # Build a 1-D alpha ramp from 0 at top to 0.75 at bottom, then darken the
    # strip in one broadcast multiply (was a per-row Python loop, ~768 iters ×
    # every frame). factor shape (rows,1,1) broadcasts over (rows, W, 3).
    ramp = np.linspace(0, 0.75, grad_end - grad_start, dtype=np.float32)
    factor = (1.0 - ramp)[:, None, None]
    strip = frame_array[grad_start:grad_end].astype(np.float32) * factor

    frame_array[grad_start:grad_end] = np.clip(strip, 0, 255).astype(np.uint8)
    return frame_array


def _ffmpeg_exe() -> str:
    """The ffmpeg binary moviepy and the tests already use (honours IMAGEIO_FFMPEG_EXE)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _build_gradient_png(path: str) -> str:
    """Writes draw_gradient_overlay() as a black RGBA scrim ffmpeg can overlay.

    Blending black at alpha a gives frame * (1 - a), which is exactly the
    multiply draw_gradient_overlay does — so it is applied once per clip by
    ffmpeg instead of once per frame in numpy.
    """
    grad_start = int(SHORTS_H * 0.60)
    ramp = np.linspace(0, 0.75, SHORTS_H - grad_start, dtype=np.float32)
    rgba = np.zeros((SHORTS_H, SHORTS_W, 4), dtype=np.uint8)
    rgba[grad_start:, :, 3] = np.round(ramp * 255).astype(np.uint8)[:, None]
    Image.fromarray(rgba, "RGBA").save(path)
    return path


def _normalize_to_portrait(
    src: str, dst: str, max_dur: float = 12.0, gradient_png: Optional[str] = None
) -> Optional[str]:
    """Re-encodes one stock clip as a 1080×1920, 30 fps, silent H.264 file.

    Cover-scales and centre-crops (no black bars), trims to `max_dur`, and
    optionally bakes in the caption scrim. Every normalised clip shares one
    format, so the final pass can join them with the concat demuxer.
    Returns `dst`, or None if ffmpeg cannot read the source.
    """
    # Trim by frame count after fps=: an input-side `-t 12` drops the last
    # frame (359 instead of 360), and the shortfall accumulated at every cut.
    # The input -t only stops ffmpeg decoding the rest of a long clip.
    chain = (f"scale={SHORTS_W}:{SHORTS_H}:force_original_aspect_ratio=increase,"
             f"crop={SHORTS_W}:{SHORTS_H},setsar=1,fps={SHORTS_FPS},"
             f"trim=end_frame={int(round(max_dur * SHORTS_FPS))}")
    cmd = [_ffmpeg_exe(), "-y", "-loglevel", "error", "-t", f"{max_dur + 1:.3f}", "-i", src]
    if gradient_png:
        cmd += ["-i", gradient_png]
        graph = f"[0:v]{chain}[v];[v][1:v]overlay=0:0,format=yuv420p[out]"
    else:
        graph = f"[0:v]{chain},format=yuv420p[out]"
    cmd += ["-filter_complex", graph, "-map", "[out]", "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", dst]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        logger.warning(f"   ⚠️ Skipping clip {src}: "
                       f"{result.stderr.decode('utf-8', 'replace').strip()[-300:]}")
        return None
    return dst


def _caption_layer(
    chunk: dict,
    active: tuple,
    font: ImageFont.FreeTypeFont,
    highlight_font: ImageFont.FreeTypeFont,
) -> Image.Image:
    """Draws one caption state on a transparent strip spanning CAPTION_AREA_TOP → bottom.

    `active` holds one flag per word in chunk["words"]: True renders that word
    highlighted (karaoke). With no per-word timing the chunk renders flat white.
    """
    img  = Image.new("RGBA", (SHORTS_W, SHORTS_H - CAPTION_AREA_TOP), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w    = SHORTS_W
    y    = int(SHORTS_H * 0.76) - CAPTION_AREA_TOP

    words_with_ts = chunk.get("words", [])

    if not words_with_ts:
        text = chunk["text"]
        bbox = draw.textbbox((0, 0), text, font=font)
        x    = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        return img

    parts = []
    for wobj, is_active in zip(words_with_ts, active):
        word = wobj["word"] + " "
        f    = highlight_font if is_active else font
        bbox = draw.textbbox((0, 0), word, font=f)
        parts.append((word, f, bbox[2] - bbox[0], is_active))

    x = (w - sum(p[2] for p in parts)) // 2
    for word, f, ww, is_active in parts:
        color = (255, 230, 0, 255) if is_active else (255, 255, 255, 255)
        draw.text((x + 2, y + 2), word, font=f, fill=(0, 0, 0, 255))
        draw.text((x, y), word, font=f, fill=color)
        x += ww
    return img


def _write_caption_track(
    chunks: List[dict],
    duration: float,
    work_dir: Path,
    font: ImageFont.FreeTypeFont,
    highlight_font: ImageFont.FreeTypeFont,
) -> str:
    """Renders each distinct caption state once; returns an ffconcat playlist timing them.

    A 60 s short is ~1,800 frames but only a few hundred caption states (one
    per highlighted word), so drawing per state instead of per frame is where
    the time goes away. The state is still looked up at every frame time, with
    the old per-frame compositor's rules: nothing before 0.4 s, the first chunk
    with start <= t <= end + 0.05, a word highlighted while start <= t <= end.
    """
    def state_at(t: float):
        if t < 0.4:
            return None
        for i, c in enumerate(chunks):
            if c["start"] <= t <= c["end"] + 0.05:
                return (i, tuple(w["start"] <= t <= w["end"] for w in c.get("words", [])))
        return None

    timeline = []  # [state, first frame], consecutive duplicates merged
    n_frames = int(round(duration * SHORTS_FPS))
    for k in range(n_frames):
        s = state_at(k / SHORTS_FPS)
        if not timeline or timeline[-1][0] != s:
            timeline.append([s, k])

    files = {}
    lines = ["ffconcat version 1.0"]
    for k, (s, first) in enumerate(timeline):
        if s not in files:
            name = f"cap_{len(files):04d}.png"
            layer = (_caption_layer(chunks[s[0]], s[1], font, highlight_font) if s
                     else Image.new("RGBA", (SHORTS_W, SHORTS_H - CAPTION_AREA_TOP), (0, 0, 0, 0)))
            layer.save(work_dir / name, compress_level=1)
            files[s] = name
        last = timeline[k + 1][1] if k + 1 < len(timeline) else n_frames
        # framerate pins the image's time base to the output frame grid; at the
        # image demuxer's default of 25 fps every switch drifted by up to a frame.
        lines += [f"file '{files[s]}'", f"option framerate {SHORTS_FPS}",
                  f"duration {(last - first) / SHORTS_FPS:.6f}"]
    # The concat demuxer drops the final entry's duration; listing it again holds it.
    lines += [f"file '{files[timeline[-1][0]]}'", f"option framerate {SHORTS_FPS}"]

    playlist = work_dir / "captions.ffconcat"
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(playlist)


def _hook_layer(
    headline: str,
    subline: str,
    title_font: ImageFont.FreeTypeFont,
    sub_font: ImageFont.FreeTypeFont,
) -> Image.Image:
    """The full-frame hook title card (scrim + text) at full opacity; ffmpeg fades it."""
    w, h = SHORTS_W, SHORTS_H
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 180))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), headline, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    hx = (w - tw) // 2
    hy = int(h * 0.38)
    draw.text((hx + 4, hy + 4), headline, font=title_font, fill=(0, 0, 0, 255))
    draw.text((hx, hy), headline, font=title_font, fill=(255, 255, 255, 255))

    bbox2 = draw.textbbox((0, 0), subline, font=sub_font)
    sx = (w - (bbox2[2] - bbox2[0])) // 2
    sy = hy + th + 28
    draw.text((sx + 3, sy + 3), subline, font=sub_font, fill=(0, 0, 0, 255))
    draw.text((sx, sy), subline, font=sub_font, fill=(255, 220, 60, 255))
    return overlay


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

class _RenderProgress(ProgressBarLogger):
    """Relay the ffmpeg render's frame count to the job event bus.

    Without this the UI sees one "Compositing..." event and then nothing,
    which reads as a hang and gets the job re-triggered. ffmpeg's
    -stats_period 5 does the throttling (proglog only throttles iter_bar).
    """

    def __init__(self, job_id: str, interval: float = 5.0):
        super().__init__(min_time_interval=interval)
        self.job_id = job_id

    def bars_callback(self, bar, attr, value, old_value=None):
        # write_videofile runs two proglog bars: "chunk" for the temp audio
        # track (seconds of work) and "frame_index" for the frames (the long
        # one). Relaying both made the UI count to 100% and restart, which
        # read as the video rendering twice. Only the frame bar is the render.
        if bar == "chunk":
            return
        total = self.bars[bar].get("total")
        if attr == "index" and total:
            pct = min(100, value * 100 // total)
            # The last frame lands minutes before the file does: ffmpeg still
            # has to flush its buffers and mux the audio track. Sitting on
            # "100%" for that tail reads as a hang, so name what is happening.
            msg = "Exporting video..." if pct == 100 else f"Rendering video... {pct}%"
            # The `progress` metric marks this as a tick that supersedes the
            # previous one, so the UI shows one updating line instead of ~180
            # stacked percentage cards. See frontend/src/events.ts.
            _emit(self.job_id, "video", "working", msg, {"progress": pct / 100})


def composite_shorts_video(
    raw_clip_paths: List[str],
    audio_path: str,
    audio_duration: float,
    caption_chunks: List[dict],
    hook: HookCard,
    output_path: str,
    job_id: str = "",
) -> bool:
    """
    Assembles the final 9:16 MP4 from raw clips + audio + captions + hook.

    Everything per-frame runs inside ffmpeg; Python only draws the images that
    change (one per caption state, one hook card). The previous MoviePy
    compositor pulled every frame through numpy/PIL and took 750–1,300 s for a
    60 s short.

    Pipeline:
      1. Normalise each clip to 1080×1920 / SHORTS_FPS with the scrim baked in
         (in parallel, one ffmpeg per clip)
      2. One ffmpeg pass: concat + loop the clips to the audio length, overlay
         the progress bar, the fading hook card and the caption track, mux audio

    Returns True on success, False on any unrecoverable error.
    """
    work = Path(tempfile.mkdtemp())
    try:
        # --------------------------------------------------------------
        # 1. Normalise clips (12 s max each, as before)
        # --------------------------------------------------------------
        logger.info("   🎞️ Normalising clips to 1080×1920...")
        gradient = _build_gradient_png(str(work / "gradient.png"))
        with ThreadPoolExecutor(max_workers=max(1, len(raw_clip_paths))) as pool:
            normalised = list(pool.map(
                lambda ip: _normalize_to_portrait(
                    ip[1], str(work / f"clip_{ip[0]}.mp4"), 12.0, gradient),
                enumerate(raw_clip_paths),
            ))
        clips = [p for p in normalised if p]
        if not clips:
            logger.error("No valid clips available for compositing.")
            return False

        footage = work / "footage.ffconcat"
        footage.write_text(
            "ffconcat version 1.0\n" + "".join(f"file '{Path(p).name}'\n" for p in clips),
            encoding="utf-8",
        )

        # --------------------------------------------------------------
        # 2. Static overlays: caption states + hook card
        # --------------------------------------------------------------
        captions = _write_caption_track(
            caption_chunks, audio_duration, work,
            _load_font(CAPTION_FONT_SIZE, bold=False),
            _load_font(CAPTION_FONT_SIZE, bold=True),
        )
        hook_png = str(work / "hook.png")
        _hook_layer(hook.headline, hook.subline,
                    _load_font(HOOK_FONT_SIZE, bold=True),
                    _load_font(HOOK_SUB_SIZE, bold=False)).save(hook_png)

        # --------------------------------------------------------------
        # 3. Final pass
        # --------------------------------------------------------------
        dur = f"{audio_duration:.3f}"
        graph = (
            f"color=c=white:s={SHORTS_W}x{PROGRESS_BAR_H}:r={SHORTS_FPS}[bar];"
            # Progress bar slides in from the left: visible width = W * t / duration
            f"[0:v][bar]overlay=x='-w+trunc(W*t/{dur})':y=0[a];"
            f"[2:v]format=rgba,"
            f"fade=t=in:st=0:d=0.4:alpha=1,"
            f"fade=t=out:st={HOOK_DURATION - 0.5}:d=0.5:alpha=1[hook];"
            f"[a][hook]overlay=0:0:eof_action=pass[b];"
            f"[b][3:v]overlay=0:{CAPTION_AREA_TOP},format=yuv420p[out]"
        )
        cmd = [
            _ffmpeg_exe(), "-y", "-loglevel", "error",
            "-nostats", "-progress", "pipe:1", "-stats_period", "5",
            # Loop the footage until -t cuts it at the audio length
            "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(footage),
            "-i", audio_path,
            "-loop", "1", "-framerate", str(SHORTS_FPS), "-t", str(HOOK_DURATION), "-i", hook_png,
            "-f", "concat", "-safe", "0", "-i", captions,
            "-filter_complex", graph,
            "-map", "[out]", "-map", "1:a",
            "-t", dur, "-r", str(SHORTS_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac",
            output_path,
        ]

        logger.info(f"   🎬 Exporting {SHORTS_W}×{SHORTS_H} portrait video → {output_path}")
        progress = _RenderProgress(job_id) if job_id else None
        if progress:
            progress(frame_index__total=int(audio_duration * SHORTS_FPS))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if progress and line.startswith("frame="):
                try:
                    progress(frame_index__index=int(line.split("=", 1)[1]))
                except ValueError:
                    pass
        stderr = proc.stderr.read()
        if proc.wait() != 0:
            logger.error(f"ffmpeg compositing failed: {stderr.strip()[-1000:]}")
            return False
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ============================================================================
# MAIN NODE
# ============================================================================

def video_generator_node(state: State) -> dict:
    """
    LangGraph node — generates a TikTok / YouTube Shorts-ready MP4.

    Reads:  state["final"], state["topic"], state["blog_folder"]
    Writes: state["video_path"]
    """

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
    # get_llm() applies the configured model and the request timeout;
    # a bare ChatOpenAI here honoured neither.
    from .utils import get_llm
    text_llm = get_llm(temperature=0.7)
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
    audio_path = generate_tts_voiceover(script)
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
    fallback_queries = [f"{topic} vertical", "abstract background portrait"]
    try:
        planner = llm.with_structured_output(VideoScenePlan)
        plan    = planner.invoke([
            SystemMessage(content=VIDEO_PLAN_SYSTEM),
            HumanMessage(content=f"Topic: {topic}\n\nVoiceover Script:\n{script}"),
        ])
        queries = plan.keywords or fallback_queries
    except Exception as e:
        # Same guard as the hook card above. This call only returns a 3-5 word
        # keyword list, but unguarded it blocks the job for the full
        # timeout x retries budget and then kills a video that already has
        # its audio and captions. The fallback queries still find footage.
        logger.warning(f"Scene planning failed ({e}), using fallback queries.")
        queries = fallback_queries
    logger.info(f"   🎥 Pexels queries: {queries}")

    # ------------------------------------------------------------------
    # 6. Fetch portrait Pexels clips
    # ------------------------------------------------------------------
    _emit(_job(state), "video", "working", f"Fetching {len(queries)} portrait stock clips...")
    # Fetched in parallel: one at a time this step took ~100 s for 5 clips.
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        fetched = list(pool.map(lambda iq: fetch_pexels_video(iq[1], temp_dir, iq[0]),
                                enumerate(queries)))
    downloaded = [p for p in fetched if p]
    logger.info(f"   ✅ Downloaded {len(downloaded)}/{len(queries)} clips")

    if not downloaded:
        fallback = fetch_pexels_video("abstract minimal portrait", temp_dir, 99)
        if fallback:
            downloaded.append(fallback)

    if not downloaded:
        logger.info("   🎨 Pexels unavailable — generating procedural ambient background clip...")
        _emit(_job(state), "video", "working", "Generating ambient background animation...")
        synthetic_path = os.path.join(temp_dir, "synthetic_bg.mp4")
        fallback_clip = create_synthetic_background_clip(audio_dur + 2.0, synthetic_path)
        if fallback_clip:
            downloaded.append(fallback_clip)

    if not downloaded:
        logger.error("No video footage available. Aborting.")
        _emit(_job(state), "video", "error", "No stock footage or background clip available.")
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
        job_id=_job(state),
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