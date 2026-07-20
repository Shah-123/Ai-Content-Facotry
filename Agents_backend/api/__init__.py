import sys
from pathlib import Path

# Ensure the backend directory is in sys.path so that absolute imports (e.g. from api.xxx) work from any CWD.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from api.main import app
from api.utils import get_job_healed

__all__ = ["app", "get_job_healed"]
