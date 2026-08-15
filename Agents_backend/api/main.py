# API Entry Point — AI Content Factory Backend
import os
import sys
import logging
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

logger = logging.getLogger("api.main")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    events.start_cleanup_task()
    yield
    events.stop_cleanup_task()

app = FastAPI(title="AI Content Factory API", version="1.0.0", lifespan=lifespan)

# CORS: defaults to the Vite dev server origins. Set ALLOWED_ORIGINS to a
# comma-separated list to override, or to "*" to restore the old open policy.
# Previously hardcoded to ["*"], which let any page on any origin drive this API.
_origins_env = (os.getenv("ALLOWED_ORIGINS") or "").strip()
_allowed_origins = (
    [o.strip() for o in _origins_env.split(",") if o.strip()]
    if _origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
# The WebSocket router checks the key itself (browsers can't set WS headers).
from api.auth import require_api_key

app.include_router(uploads_router, dependencies=[Depends(require_api_key)])
app.include_router(websocket_router)
app.include_router(jobs_router, dependencies=[Depends(require_api_key)])

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

