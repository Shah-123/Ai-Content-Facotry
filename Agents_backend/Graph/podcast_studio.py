import os
import time
import random
import re
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Literal

from Graph.agents.utils import logger, _job, _emit, llm_quality

# ============================================================================
# CONSTANTS
# ============================================================================

_TTS_MAX_ATTEMPTS = 3
_TTS_BACKOFF_BASE = 2

# Voice assignments: distinct OpenAI voices for each host
# nova = bright/energetic (Host A),  onyx = deep/warm (Host B)
_VOICE_MAP = {
    "Host A": "nova",
    "Host B": "onyx",
}

# ============================================================================
# PYDANTIC DIALOGUE SCHEMA
# ============================================================================

class DialogueTurn(BaseModel):
    speaker: Literal["Host A", "Host B"] = Field(
        description="The speaker of this turn. Must be either 'Host A' or 'Host B'."
    )
    text: str = Field(
        description=(
            "The dialogue spoken by the host. Speak naturally as if in a podcast. "
            "Use conversational language, contractions, and filler words like "
            "'you know', 'right?', 'hmm', 'well', 'exactly'."
        )
    )

class PodcastScript(BaseModel):
    title: str = Field(description="An engaging title for this podcast episode.")
    turns: List[DialogueTurn] = Field(
        description="List of alternating dialogue turns discussing the blog content."
    )


# ============================================================================
# HELPER: lazy OpenAI client
# ============================================================================

def _get_openai_client():
    """
    Lazy initialisation of the OpenAI client.
    Called at function runtime so load_dotenv() in main.py runs first.
    """
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — cannot generate podcast audio.")
        return None
    return OpenAI(api_key=api_key)


def _get_audio_file_clip():
    """Import and return AudioFileClip with MoviePy v1/v2 compatibility."""
    try:
        from moviepy import AudioFileClip
        return AudioFileClip
    except ImportError:
        try:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            return AudioFileClip
        except ImportError:
            logger.error("Could not import AudioFileClip from moviepy.")
            return None


# ============================================================================
# PODCAST AUDIO GENERATION
# ============================================================================

def generate_podcast_audio(state: dict, output_path: str) -> bool:
    """
    Generate a 2-speaker dialogue podcast using:
      1. LLM (llm_quality / GPT-4o) for scriptwriting
      2. OpenAI TTS (tts-1-hd) for audio synthesis
    Outputs a single merged audio file at `output_path` (MP3 or WAV).
    """
    client = _get_openai_client()
    if not client:
        return False

    plan  = state.get("plan")
    topic = state.get("topic", "the topic")

    # ── Build outline/context ─────────────────────────────────────────────
    sections_summary = ""
    if plan and hasattr(plan, "tasks"):
        sections_summary = "\n".join(
            f"- {task.title}: {getattr(task, 'goal', getattr(task, 'description', ''))}"
            for task in plan.tasks
            if hasattr(task, "title")
        )
    elif state.get("merged_md"):
        # Up to 6 000 chars so the LLM has enough material for a longer episode
        sections_summary = state["merged_md"][:6000]

    # ── Script prompt ─────────────────────────────────────────────────────
    script_prompt = f"""You are a professional podcast scriptwriter. Create an engaging, conversational 2-speaker podcast episode based on the following blog content.

Blog Title: "{plan.blog_title if plan else topic}"
Audience: {plan.audience if plan else "general"}
Tone: {plan.tone if plan else "conversational"}

Key Content/Outline:
{sections_summary}

Roles:
- Host A: Energetic, curious, guides the conversation. Asks probing follow-up questions.
- Host B: Warm, expert, provides depth, real-world examples, and nuanced analysis.

TARGET LENGTH: 6 to 7 minutes of spoken audio.
At a natural speaking pace of ~130 words per minute, this requires roughly 780–910 total words across ALL turns combined.

Structure the episode as follows (18–20 dialogue turns total):

1. OPENING (3 turns): Host A welcomes listeners with an energetic hook about why this topic matters today. Host B adds a surprising stat or counter-intuitive angle. Host A sets up the agenda for the episode.

2. FIRST DEEP DIVE (4–5 turns): Explore the first major theme from the outline. Host A asks a specific question; Host B answers with detail and an anecdote or real-world example. They go back and forth.

3. SECOND DEEP DIVE (4–5 turns): Explore the second major theme. Include a moment where Host A pushes back or asks "but what about...?" and Host B defends or refines the point.

4. KEY TAKEAWAY DISCUSSION (3–4 turns): Synthesise the most actionable or surprising insights. Both hosts share their personal "aha moment" from the topic.

5. CLOSING (2 turns): Host B summarises the three key things listeners should remember. Host A thanks Host B and the listeners with energy and a call to action.

Guidelines:
- Each turn MUST be 70–110 words long. Do not write shorter turns.
- Write naturally spoken dialogue — use contractions, occasional "you know", "right?", "hmm", "that's fascinating", "exactly", etc.
- Avoid bullet points or lists in the speech; keep it flowing and conversational.
- Vary sentence length within each turn for a natural cadence.
- Do NOT include stage directions, sound effects, or music cues.
"""

    # ── Generate script via LLM ───────────────────────────────────────────
    try:
        logger.info("🎙️ Generating 2-Speaker Podcast script using LLM...")
        script_generator = llm_quality.with_structured_output(PodcastScript)
        script: PodcastScript = script_generator.invoke(script_prompt)
        logger.info(
            f"   ✅ Script generated — {len(script.turns)} turns, title: '{script.title}'"
        )
    except Exception as e:
        logger.error(f"   ❌ Script generation failed: {e}")
        return False

    # ── Synthesise each turn with OpenAI TTS ─────────────────────────────
    import io
    import wave as wave_lib

    audio_segments: list[bytes] = []   # raw PCM frames for each turn

    for idx, turn in enumerate(script.turns):
        voice    = _VOICE_MAP.get(turn.speaker, "nova")
        turn_txt = turn.text.strip()
        if not turn_txt:
            continue

        logger.info(
            f"🎙️ Synthesising turn {idx + 1}/{len(script.turns)} "
            f"({turn.speaker} → voice: {voice})..."
        )

        success = False
        for attempt in range(1, _TTS_MAX_ATTEMPTS + 1):
            try:
                # OpenAI TTS — returns raw MP3/PCM bytes directly
                response = client.audio.speech.create(
                    model="tts-1-hd",       # high-quality model
                    voice=voice,
                    input=turn_txt,
                    response_format="pcm",  # 24 kHz, 16-bit, mono — matches WAV params
                )
                audio_segments.append(response.content)
                logger.info(f"   ✅ Turn {idx + 1} synthesised ({len(response.content):,} bytes).")
                success = True
                break

            except Exception as e:
                err = str(e)
                logger.warning(f"   ⚠️ Turn {idx + 1} attempt {attempt} failed: {e}")
                if attempt < _TTS_MAX_ATTEMPTS:
                    wait = (_TTS_BACKOFF_BASE ** attempt) + random.random()
                    logger.info(f"   ⏳ Retrying in {wait:.1f}s...")
                    time.sleep(wait)

        if not success:
            logger.error(f"   ❌ Turn {idx + 1} failed after {_TTS_MAX_ATTEMPTS} attempts.")
            return False

    # ── Merge all PCM segments into a single WAV ──────────────────────────
    if not audio_segments:
        logger.error("   ❌ No audio segments produced.")
        return False

    # If output_path is .mp3, we write to a temporary WAV file first and then convert it.
    is_mp3 = output_path.lower().endswith(".mp3")
    wav_path = output_path.replace(".mp3", "_temp.wav") if is_mp3 else output_path

    try:
        logger.info(f"🎙️ Writing merged WAV → {wav_path}")
        # 0.3s of silence at 24000 Hz, 16-bit mono: 24000 * 0.3 * 2 = 14400 bytes
        silence_bytes = b"\x00" * 14400

        with wave_lib.open(wav_path, "wb") as wf:
            # OpenAI PCM: 24 000 Hz, 16-bit (2 bytes), mono
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            for idx, segment in enumerate(audio_segments):
                if idx > 0:
                    wf.writeframes(silence_bytes)
                wf.writeframes(segment)
        logger.info("   ✅ Podcast WAV written successfully.")

        if is_mp3:
            AudioFileClip = _get_audio_file_clip()
            if AudioFileClip is None:
                logger.error("   ❌ MoviePy AudioFileClip not available. Cannot convert to MP3.")
                if os.path.exists(wav_path):
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass
                return False

            logger.info(f"🎙️ Converting temporary WAV to MP3: {wav_path} -> {output_path}")
            clip = None
            try:
                clip = AudioFileClip(wav_path)
                clip.write_audiofile(output_path, codec="libmp3lame")
            except Exception as conv_err:
                logger.error(f"   ❌ MP3 conversion failed: {conv_err}")
                return False
            finally:
                if clip is not None:
                    try:
                        clip.close()
                    except Exception:
                        pass
                # Clean up the temporary WAV file
                if os.path.exists(wav_path):
                    try:
                        os.remove(wav_path)
                    except Exception as rm_err:
                        logger.warning(f"   ⚠️ Failed to remove temporary WAV file: {rm_err}")

        return True

    except Exception as e:
        logger.error(f"   ❌ Failed to write audio file: {e}")
        return False


# ============================================================================
# LANGGRAPH NODE
# ============================================================================

def podcast_node(state: dict) -> dict:
    """
    LangGraph node: generate podcast audio from blog content using OpenAI TTS.
    Returns: {"podcast_audio_path": str | None}
    """
    _emit(_job(state), "podcast_generator", "started", "Generating AI Podcast Audio via OpenAI TTS...")
    logger.info("--- 🎙️ PODCAST STATION (OpenAI TTS) ---")

    # Setup output directory
    blog_folder = state.get("blog_folder")
    podcast_dir = Path(blog_folder) / "audio" if blog_folder else Path("generated_podcasts")
    podcast_dir.mkdir(parents=True, exist_ok=True)

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = podcast_dir / f"podcast_{timestamp}.mp3"

    logger.info("   ✍️  Synthesising Podcast Audio via OpenAI TTS...")
    success = generate_podcast_audio(state, str(final_path))

    if success:
        logger.info(f"   ✅ Podcast saved → {final_path}")
        _emit(_job(state), "podcast_generator", "completed", "Podcast audio generated successfully.")
        return {"podcast_audio_path": str(final_path)}
    else:
        logger.error("   ❌ Podcast generation failed.")
        _emit(_job(state), "podcast_generator", "error", "Failed to generate podcast audio.")
        return {"podcast_audio_path": None}