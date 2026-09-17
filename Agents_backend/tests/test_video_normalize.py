import sys
import subprocess
from pathlib import Path

import pytest

# Add parent directory to sys.path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from Graph.agents.video import _normalize_to_portrait, SHORTS_W, SHORTS_H

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")


def _probe(path):
    """Returns (width, height) of the first video stream via ffmpeg's own output."""
    out = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
    ).stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        if "Video:" in line:
            for token in line.split(","):
                token = token.strip().split(" ")[0]
                if "x" in token:
                    w, _, h = token.partition("x")
                    if w.isdigit() and h.isdigit():
                        return int(w), int(h)
    raise AssertionError(f"no video stream found in ffmpeg output:\n{out}")


@pytest.mark.parametrize("src_size", ["640x480", "1000x1200", "2160x3840"])
def test_normalize_fills_portrait_frame(tmp_path, src_size):
    """Landscape, mild-portrait and oversized 9:16 sources all come out 1080x1920."""
    src = tmp_path / f"src_{src_size}.mp4"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=s={src_size}:r=30:d=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True,
    )

    dst = _normalize_to_portrait(str(src), str(tmp_path / "out.mp4"))

    assert dst is not None, "ffmpeg normalise returned None"
    assert _probe(dst) == (SHORTS_W, SHORTS_H)


def test_normalize_returns_none_on_bad_input(tmp_path):
    """A file ffmpeg can't decode must return None so the caller falls back."""
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"definitely not a video")
    assert _normalize_to_portrait(str(junk), str(tmp_path / "out.mp4")) is None


def _first_frame_rgb(path):
    """Decodes frame 0 of a video as a (H, W, 3) uint8 RGB array."""
    import numpy as np
    raw = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(path),
         "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(SHORTS_H, SHORTS_W, 3)


@pytest.mark.parametrize("level", [60, 128, 200])
def test_baked_gradient_matches_python_overlay(tmp_path, level):
    """The ffmpeg scrim must reproduce draw_gradient_overlay's arithmetic."""
    import numpy as np
    from Graph.agents.video import _build_gradient_png, draw_gradient_overlay

    # Flat colour: scaling is a no-op and x264 reproduces it almost exactly,
    # so any difference that shows up is the gradient maths, not codec noise.
    src = tmp_path / f"flat_{level}.mp4"
    hexc = f"0x{level:02x}{level:02x}{level:02x}"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={hexc}:s={SHORTS_W}x{SHORTS_H}:r=30:d=1",
         "-c:v", "libx264", "-crf", "0", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True,
    )

    grad = _build_gradient_png(str(tmp_path / "gradient.png"))
    dst = _normalize_to_portrait(
        str(src), str(tmp_path / "out.mp4"), max_dur=1.0, gradient_png=grad
    )
    assert dst is not None

    got = _first_frame_rgb(dst).astype(int)
    want = draw_gradient_overlay(
        np.full((SHORTS_H, SHORTS_W, 3), level, dtype=np.uint8)
    ).astype(int)

    diff = np.abs(got - want)
    assert diff.mean() < 2.0, f"mean diff {diff.mean():.2f} too high"
    assert diff.max() < 8, f"max diff {diff.max()} too high"


def test_gradient_png_is_transparent_above_the_ramp(tmp_path):
    """Top 60% of the frame must be untouched by the scrim."""
    import numpy as np
    from PIL import Image
    from Graph.agents.video import _build_gradient_png

    alpha = np.array(Image.open(_build_gradient_png(str(tmp_path / "g.png"))))[:, :, 3]
    cut = int(SHORTS_H * 0.60)
    assert alpha[:cut].max() == 0
    assert alpha[cut].max() == 0                # ramp starts at zero
    assert 188 <= alpha[-1].min() <= 194        # 0.75 * 255
    assert np.all(np.diff(alpha[cut:, 0]) >= 0)  # monotonic
