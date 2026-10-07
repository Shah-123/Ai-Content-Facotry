"""
Latency guards: independent network calls must overlap, not queue.

Each stage below makes calls that do not depend on one another — image
generations, per-section rewrites, DeepEval rubrics, podcast turns, and the
video's hook / voiceover / footage chains. Run one after another, the wait is
the SUM of the calls; run together it is the slowest one.

Every fake call waits on a threading.Barrier sized to the number of calls, so
the barrier only opens if they are all in flight at once. A regression back to
a sequential loop leaves the first call stuck until the 5s timeout, which
breaks the barrier and fails the test — no timing assertions, no flakiness.
"""

import re
import sys
import threading
import types
import wave
from types import SimpleNamespace


def _barrier(parties: int) -> threading.Barrier:
    return threading.Barrier(parties, timeout=5)


def test_images_are_generated_concurrently_and_placed_in_order(tmp_path, monkeypatch):
    from Graph.agents import multimedia

    barrier = _barrier(2)

    def fake_generate(prompt, **_):
        barrier.wait()
        return prompt.encode()

    monkeypatch.setattr(multimedia, "_generate_image_multi_provider", fake_generate)
    out = multimedia.generate_and_place_images({
        "blog_folder": str(tmp_path),
        "merged_md": "# T\n\nFirst para.\n\nSecond para.\n\nThird para.",
        "image_specs": [
            {"prompt": "p1", "filename": "one", "alt": "one", "target_paragraph": "Second para."},
            {"prompt": "p2", "filename": "two", "alt": "two", "target_paragraph": "Third para."},
        ],
    })

    md = out["final"]
    assert md.index("Second para.") < md.index("![one]") < md.index("Third para.") < md.index("![two]")
    assert (tmp_path / "assets" / "images" / "one.png").read_bytes() == b"p1"
    assert (tmp_path / "assets" / "images" / "2_two.png").read_bytes() == b"p2"


def test_flagged_sections_are_revised_concurrently(monkeypatch):
    from Graph.agents import revision, utils

    barrier = _barrier(2)

    class FakeLLM:
        def invoke(self, messages):
            barrier.wait()
            title = re.search(r"SECTION TITLE: (.+)", messages[1].content).group(1)
            return SimpleNamespace(content=f"Revised {title}. " * 20)

    monkeypatch.setattr(utils, "llm_quality", FakeLLM())
    final = (
        "# Title\n\n"
        "## Alpha\n\n" + "Alpha claim sentence here. " * 10 + "\n\n"
        "## Beta\n\n" + "Beta claim sentence here. " * 10
    )
    out = revision.revision_node({
        "final": final,
        "qa_issues": [
            {"severity": "critical", "claim": "Alpha claim"},
            {"severity": "critical", "claim": "Beta claim"},
        ],
    })

    text = out["final"]
    assert text.index("## Alpha") < text.index("Revised Alpha.") < text.index("## Beta") < text.index("Revised Beta.")
    assert "claim sentence" not in text
    assert out["revision_count"] == 1


def test_deepeval_rubrics_are_measured_concurrently(monkeypatch):
    barrier = _barrier(4)

    class FakeGEval:
        def __init__(self, name, **_):
            self.name = name

        def measure(self, test_case):
            barrier.wait()
            self.score, self.reason = 0.8, f"{self.name} ok"

    # Stub the library so the test never imports deepeval's telemetry.
    metrics = types.ModuleType("deepeval.metrics")
    metrics.GEval = FakeGEval
    test_case = types.ModuleType("deepeval.test_case")
    test_case.LLMTestCase = lambda **kw: kw
    test_case.LLMTestCaseParams = SimpleNamespace(
        INPUT="input", ACTUAL_OUTPUT="actual_output", RETRIEVAL_CONTEXT="retrieval_context"
    )
    monkeypatch.setitem(sys.modules, "deepeval", types.ModuleType("deepeval"))
    monkeypatch.setitem(sys.modules, "deepeval.metrics", metrics)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", test_case)

    from Graph.agents.evaluation import deepeval_evaluation_node

    scores = deepeval_evaluation_node({"final": "An article.", "topic": "t"})["deepeval_scores"]

    rubrics = ("coherence", "relevance", "accuracy", "tone_alignment")
    assert [scores[k]["score"] for k in rubrics] == [0.8] * 4
    assert scores["tone_alignment"]["reasoning"] == "Tone Alignment ok"
    assert scores["overall_score"] == 0.8


def test_podcast_fallback_synthesises_turns_concurrently_in_order(tmp_path, monkeypatch):
    from Graph import podcast_studio as ps

    script = ps.PodcastScript(title="t", turns=[
        ps.DialogueTurn(speaker="Host A" if i % 2 == 0 else "Host B", text=f"turn {i}")
        for i in range(3)
    ])
    generator = SimpleNamespace(invoke=lambda _: script)
    monkeypatch.setattr(ps, "llm_quality", SimpleNamespace(with_structured_output=lambda _: generator))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)  # straight to the OpenAI TTS fallback

    barrier = _barrier(3)

    def create(model, voice, input, response_format):
        barrier.wait()
        return SimpleNamespace(content=input.encode())  # "PCM" that names its turn

    client = SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=create)))
    monkeypatch.setattr(ps, "_get_openai_client", lambda: client)

    out = tmp_path / "podcast.wav"
    assert ps.generate_podcast_audio({"topic": "t"}, str(out))

    with wave.open(str(out)) as wf:
        frames = wf.readframes(wf.getnframes())
    assert frames == (b"\x00" * 14400).join([b"turn 0", b"turn 1", b"turn 2"])


def test_video_prep_chains_run_concurrently(tmp_path, monkeypatch):
    from Graph.agents import utils, video

    barrier = _barrier(3)  # hook card, voiceover and scene planning must overlap

    def hook_card(topic, script):
        barrier.wait()
        return video.HookCard(headline="h", subline="s")

    def tts(script, voice=None):
        barrier.wait()
        return str(tmp_path / "voice.wav")

    class Planner:
        def invoke(self, _):
            barrier.wait()
            return video.VideoScenePlan(keywords=["a", "b"])

    audio_mod = types.ModuleType("moviepy.audio.io.AudioFileClip")
    audio_mod.AudioFileClip = lambda path: SimpleNamespace(duration=30.0)
    monkeypatch.setitem(sys.modules, "moviepy.audio.io.AudioFileClip", audio_mod)
    monkeypatch.setattr(utils, "get_llm", lambda **_: SimpleNamespace(
        invoke=lambda _: SimpleNamespace(content="the script")))
    monkeypatch.setattr(video, "_build_voiceover_brief", lambda *_: "brief")
    monkeypatch.setattr(video, "_generate_hook_card", hook_card)
    monkeypatch.setattr(video, "generate_tts_voiceover", tts)
    monkeypatch.setattr(video, "get_word_timestamps", lambda *_, **__: [])
    monkeypatch.setattr(video, "llm", SimpleNamespace(with_structured_output=lambda _: Planner()))
    monkeypatch.setattr(video, "fetch_pexels_video", lambda q, d, i: f"clip_{i}")
    composed = {}
    monkeypatch.setattr(video, "composite_shorts_video", lambda **kw: composed.update(kw) or True)

    out = video.video_generator_node({"topic": "t", "final": "blog", "blog_folder": str(tmp_path)})

    assert out["video_path"].endswith("short.mp4")
    assert composed["raw_clip_paths"] == ["clip_0", "clip_1"]
    assert composed["audio_duration"] == 30.0
    assert composed["hook"].headline == "h"


def test_pexels_downloads_the_rendition_matching_the_output(tmp_path, monkeypatch):
    """The first top-scoring file used to win: here the UHD one, ~11x slower per frame."""
    from Graph.agents import video

    files = [
        {"width": 2160, "height": 3840, "link": "uhd"},
        {"width": 720, "height": 1280, "link": "hd720"},
        {"width": 1080, "height": 1920, "link": "fhd"},
    ]
    downloaded = []

    class Resp:
        def __init__(self, link):
            self.link = link

        def raise_for_status(self):
            pass

        def json(self):
            return {"videos": [{"video_files": files}]}

        def __enter__(self):
            downloaded.append(self.link)
            return self

        def __exit__(self, *_):
            return False

        def iter_content(self, chunk_size):
            yield b"x"

    monkeypatch.setenv("PEXELS_API_KEY", "k")
    monkeypatch.setattr(video.requests, "get", lambda url, **kw: Resp(url if kw.get("stream") else None))

    assert video.fetch_pexels_video("q", str(tmp_path), 0)
    assert downloaded == ["fhd"]
