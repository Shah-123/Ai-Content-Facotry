import os
import sys
import logging
from pathlib import Path

from fastapi import FastAPI
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── serve static frontend ──────────────────────────────────────────────────
_FRONTEND = _BACKEND_DIR.parent / "frontend"
if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")
else:
    logger.warning(f"Frontend directory not found at {_FRONTEND}. UI will not be available.")

# ── ROOT → index.html ──────────────────────────────────────────────────────
@app.get("/")
async def root():
    index = _FRONTEND / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "AI Content Factory API running"})

# Include all the sub-routers
app.include_router(uploads_router)
app.include_router(websocket_router)
app.include_router(jobs_router)
