"""Images and podcast turns are generated concurrently but assembled in order."""
import time
import wave

from Graph.agents import multimedia
import Graph.podcast_studio as podcast


def test_images_generate_concurrently_and_keep_spec_order(tmp_path, monkeypatch):
    def slow_provider(prompt, **_):
        time.sleep(0.5 if prompt == "first" else 0.1)   # the hero finishes LAST
        return prompt.encode()

    monkeypatch.setattr(multimedia, "_generate_image_multi_provider", slow_provider)
    state = {
        "blog_folder": str(tmp_path),
        "merged_md": "# Title\n\nIntro paragraph.\n\nBody paragraph.",
        "image_specs": [{"prompt": "first", "filename": "hero"},
                        {"prompt": "second", "filename": "body"}],
    }

    start = time.perf_counter()
    out = multimedia.generate_and_place_images(state)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.55, f"images ran one after another ({elapsed:.2f}s)"
    images = tmp_path / "assets" / "images"
    assert (images / "hero.png").read_bytes() == b"first"
    assert (images / "2_body.png").read_bytes() == b"second"
    md = out["final"]
    assert md.index("hero.png") < md.index("Intro paragraph") < md.index("2_body.png")


def test_podcast_turns_synthesise_concurrently_in_script_order(tmp_path, monkeypatch):
    script = podcast.PodcastScript(title="T", turns=[
        podcast.DialogueTurn(speaker="Host A" if i % 2 == 0 else "Host B", text=f"turn {i}")
        for i in range(6)
    ])

    class FakeLLM:
        def with_structured_output(self, _):
            return self

        def invoke(self, _):
            return script

    class FakeSpeech:
        def create(self, input, **_):
            i = int(input.split()[1])
            time.sleep(0.3 - i * 0.04)          # later turns finish first
            return type("R", (), {"content": bytes([i]) * 100})()

    class FakeClient:
        audio = type("A", (), {"speech": FakeSpeech()})()

    monkeypatch.setattr(podcast, "llm_quality", FakeLLM())
    monkeypatch.setattr(podcast, "_get_openai_client", lambda: FakeClient())
    monkeypatch.setattr(podcast, "_emit", lambda *a, **k: None)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    out = tmp_path / "pod.wav"
    start = time.perf_counter()
    assert podcast.generate_podcast_audio({"topic": "x"}, str(out))
    elapsed = time.perf_counter() - start

    assert elapsed < 0.9, f"turns ran one after another ({elapsed:.2f}s)"
    with wave.open(str(out)) as wf:
        pcm = wf.readframes(wf.getnframes())
    silence = b"\x00" * 14400
    assert pcm == silence.join(bytes([i]) * 100 for i in range(6))
