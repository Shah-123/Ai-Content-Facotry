"""Long media renders must keep emitting progress, or the UI reads as hung."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import Graph.agents.video as video


def _capture(monkeypatch):
    messages = []
    monkeypatch.setattr(video, "_emit", lambda job, agent, status, msg, *a: messages.append(msg))
    return messages


def test_render_progress_reports_percentage(monkeypatch):
    messages = _capture(monkeypatch)
    reporter = video._RenderProgress("job123", interval=0)
    reporter.bars["t"] = dict(title="t", index=-1, total=200, message=None, indent=0)

    for index in (0, 50, 200):
        reporter.bars_callback("t", "index", index)

    assert messages == [
        "Rendering video... 0%",
        "Rendering video... 25%",
        "Exporting video...",   # frame bar done; ffmpeg is still muxing
    ]


def test_render_progress_ignores_unstarted_bars(monkeypatch):
    """moviepy reports bars before their total is known — that must not divide by zero."""
    messages = _capture(monkeypatch)
    reporter = video._RenderProgress("job123", interval=0)
    reporter.bars["chunk"] = dict(title="chunk", index=-1, total=None, message=None, indent=0)

    reporter.bars_callback("chunk", "index", 5)
    reporter.bars_callback("chunk", "message", 5)

    assert messages == []
