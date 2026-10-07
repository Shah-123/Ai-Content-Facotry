# API Entry Point — AI Content Factory Backend
import os
import sys
import logging
import threading
from pathlib import Path

# Force UTF-8 encoding for stdout/stderr to prevent CP1252/charmap crashes on Windows when printing emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure the backend directory is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR.parent / ".env")

import event_bus as events

# Import sub-routers
from api.routes.uploads import router as uploads_router
from api.routes.websocket import router as websocket_router
from api.routes.jobs import router as jobs_router
from api.users import router as auth_router

logger = logging.getLogger("api.main")

from contextlib import asynccontextmanager

def _warm_imports() -> None:
    """Pay the pipeline's import cost at boot instead of on the first request.

    The first POST /api/jobs imported the whole agents package inside its async
    handler: about 3s on the event loop, during which every WebSocket and every
    other request stalled.
    """
    try:
        import Graph.nodes  # noqa: F401  (builds the LLM clients, so it needs OPENAI_API_KEY)
        from api.background import _get_pipeline_main
        _get_pipeline_main()
    except Exception as exc:  # e.g. no key yet: the first request reports it, as before
        logger.warning(f"Import warm-up skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.start_cleanup_task()
    if os.getenv("WARMUP_IMPORTS", "1") != "0":
        threading.Thread(target=_warm_imports, name="warm-imports", daemon=True).start()
    yield
    events.stop_cleanup_task()

app = FastAPI(title="AI Content Factory API", version="1.0.0", lifespan=lifespan)

# CORS: defaults to the Vite dev server origins. Set ALLOWED_ORIGINS to a
# comma-separated list to override, or to "*" to restore the old open policy.
# Previously hardcoded to ["*"], which let any page on any origin drive this API.
from api.auth import allowed_origins

_allowed_origins = allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # The session cookie needs credentialed CORS — but never with "*", which
    # would let ANY website make signed-in requests as the visitor. With "*"
    # the browser simply won't send the cookie cross-origin.
    allow_credentials="*" not in _allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"Unhandled server exception at {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )

# Include all the sub-routers first so API routes take precedence.
# `require_api_key` is a no-op unless API_KEY is set in .env — see api/auth.py.
# `require_job_owner` scopes every jobs route to the signed-in account: any
# {job_id} that isn't theirs is a 404. The WebSocket router checks both itself
# (browsers can't set WS headers).
from api.auth import require_api_key
from api.users import require_job_owner, require_user

app.include_router(auth_router, dependencies=[Depends(require_api_key)])
app.include_router(uploads_router, dependencies=[Depends(require_api_key), Depends(require_user)])
app.include_router(websocket_router)
app.include_router(jobs_router, dependencies=[Depends(require_api_key), Depends(require_job_owner)])

# ── serve static frontend ──────────────────────────────────────────────────
_FRONTEND = _BACKEND_DIR.parent / "frontend"
_DIST = _FRONTEND / "dist"
_SRC = _FRONTEND / "src"

if _DIST.exists() and (_DIST / "index.html").exists():
    # Production built frontend
    if (_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="dist-assets")
    
    @app.get("/")
    async def root():
        return FileResponse(str(_DIST / "index.html"))
elif _FRONTEND.exists():
    # Dev mode: mount /src and /public if present so raw index.html references work
    if _SRC.exists():
        app.mount("/src", StaticFiles(directory=str(_SRC)), name="frontend-src")
    if (_FRONTEND / "public").exists():
        app.mount("/public", StaticFiles(directory=str(_FRONTEND / "public")), name="frontend-public")
    if (_FRONTEND / "node_modules").exists():
        app.mount("/node_modules", StaticFiles(directory=str(_FRONTEND / "node_modules")), name="frontend-node-modules")

    @app.get("/")
    async def root():
        index = _FRONTEND / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"status": "AI Content Factory API running"})
else:
    @app.get("/")
    async def root():
        return JSONResponse({"status": "AI Content Factory API running"})

