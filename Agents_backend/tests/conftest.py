"""
Test Configuration
==================
Sets up sys.path, environment variables, and sys.modules stubs so that
test imports resolve correctly WITHOUT triggering any API calls or sys.exit().

Strategy: stub out heavy optional dependencies that are not installed in the
test environment (google-genai, moviepy, PIL, BS4, twikit) using MagicMock
objects BEFORE any project code is imported. This is the standard pattern for
testing code that conditionally uses optional libraries.
"""
import os
import sys
from unittest.mock import MagicMock

# ===========================================================================
# 1. Ensure Agents_backend is on the import path
# ===========================================================================
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ===========================================================================
# 2. Set dummy API keys BEFORE any project code is imported.
#    main.py calls sys.exit(1) if OPENAI_API_KEY is missing at import time.
# ===========================================================================
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-dummy-key")
os.environ.setdefault("GOOGLE_API_KEY", "AIzaSy-test-dummy-key")
os.environ.setdefault("PEXELS_API_KEY", "test-dummy-pexels-key")

# ===========================================================================
# 3. Stub out heavy optional dependencies that are NOT installed in the
#    test environment. Must happen BEFORE importing any project module.
# ===========================================================================

def _mock_module(*names):
    """Register MagicMock stubs for each dotted module name and all parents."""
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            key = ".".join(parts[:i])
            if key not in sys.modules:
                sys.modules[key] = MagicMock()

# google-genai (used by video.py, podcast_studio.py, multimedia.py)
_mock_module(
    "google",
    "google.genai",
    "google.genai.types",
    "google.auth",
    "google.auth.credentials",
)

# moviepy (used by video.py)
_mock_module(
    "moviepy",
    "moviepy.editor",
    "moviepy.video",
    "moviepy.video.io",
    "moviepy.video.io.VideoFileClip",
    "moviepy.audio",
    "moviepy.audio.io",
)

# PIL / Pillow (used by video.py)
_mock_module("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont")

# BeautifulSoup (used by research.py) — may or may not be installed
try:
    import bs4  # noqa: F401
except ImportError:
    _mock_module("bs4")

# twikit (in requirements but not used by any tested module)
_mock_module("twikit")

# webvtt (used by video.py subtitle generation)
_mock_module("webvtt")
