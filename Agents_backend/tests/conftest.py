"""
Test Configuration
==================
Sets up sys.path, environment variables, and sys.modules stubs so that
test imports resolve correctly WITHOUT triggering any API calls or sys.exit().

Strategy: stub out heavy optional dependencies that are not installed in the
test environment (moviepy, PIL, BS4, twikit) using MagicMock
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
# 1b. Never touch the real data/ folder.
#
#    db.py migrates DB_PATH and api/users.py assigns ownerless jobs AT IMPORT
#    TIME, and the event bus appends to data/events/. Before these overrides,
#    simply running the suite migrated the developer's real web_jobs.db and
#    left test event logs beside real ones. Fixtures still swap in their own
#    per-test files on top of this.
# ===========================================================================
import tempfile

_TEST_DATA = tempfile.mkdtemp(prefix="acf-tests-")
os.environ["WEB_JOBS_DB"] = os.path.join(_TEST_DATA, "web_jobs.db")
os.environ["EVENTS_DIR"] = os.path.join(_TEST_DATA, "events")

# ===========================================================================
# 2. API keys.
#
#    The golden harness makes REAL API calls, so it needs the real keys from
#    .env. Everything else must never reach a live API, so it gets dummies.
#
#    Order matters and is easy to get wrong: `setdefault` below wins over a
#    later `load_dotenv()`, because load_dotenv defaults to override=False.
#    Loading .env here FIRST (only when the golden tests are enabled) is what
#    lets the real key through — otherwise every golden run 401s on a dummy.
# ===========================================================================
if os.getenv("RUN_GOLDEN_TESTS") == "1":
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# Fallbacks for the ordinary (mocked) test run. main.py exits if
# OPENAI_API_KEY is missing at import time, so one must always be present.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-dummy-key")
os.environ.setdefault("PEXELS_API_KEY", "test-dummy-pexels-key")

# ===========================================================================
# 3. Stub out heavy optional dependencies that are NOT installed in the
#    test environment. Must happen BEFORE importing any project module.
# ===========================================================================

def _mock_module(*names):
    """Register MagicMock stubs for each dotted module name and all parents —
    only when the package is NOT installed.

    It used to stub unconditionally, skipping only modules already imported.
    PIL was "already imported" solely because the google-genai package pulled
    it in during startup, so the video tests that need real Pillow passed by
    accident and broke the moment google-genai was uninstalled.
    """
    import importlib.util
    for name in names:
        if importlib.util.find_spec(name.split(".")[0]) is not None:
            continue  # the real package is available; use it
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            key = ".".join(parts[:i])
            if key not in sys.modules:
                sys.modules[key] = MagicMock()

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
