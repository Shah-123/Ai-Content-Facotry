"""
Real-Time Event Bus for Agent Visualization
Lightweight pub/sub system using asyncio.Queue.
Agent nodes push events → WebSocket endpoint streams them to the frontend.
Events are also persisted to disk so historical logs are retained.
"""

import asyncio
import time
import logging
import json
import os
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger("event_bus")

# ============================================================================
# EVENT DATA MODEL
# ============================================================================

@dataclass
class AgentEvent:
    """A single event emitted by an agent node."""
    job_id: str
    agent_name: str
    status: str          # "started", "working", "completed", "error"
    message: str
    timestamp: float
    metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["metrics"] is None:
            d["metrics"] = {}
        return d


# ============================================================================
# GLOBAL EVENT BUS & STORAGE
# ============================================================================

# Stores: job_id -> list of subscriber queues
_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)

# Cache the main event loop so background threads can use call_soon_threadsafe
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# Per-job file locks to prevent concurrent read/write on .jsonl files
_file_locks: Dict[str, threading.Lock] = {}

_DATA_DIR = Path(__file__).parent / "data" / "events"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Active manual tasks currently running in the process
_active_tasks = set()

# Jobs already scanned for restart-orphaned tasks in THIS process. Orphan
# detection only needs to run once per job per process: a task killed by a
# server restart is caught on the first reconnect, and any task that dies while
# the process is alive always writes its own terminal (completed/error) event.
# This guard turns the per-reconnect whole-file re-scan-and-append into a
# one-time cost.
_healed_jobs: set = set()
_heal_lock = threading.Lock()

def register_active_task(job_id: str, task_name: str) -> bool:
    """Register a manual task as currently running in memory. Returns False if already active."""
    key = (job_id, task_name)
    if key in _active_tasks:
        return False
    _active_tasks.add(key)
    return True

def unregister_active_task(job_id: str, task_name: str):
    """Unregister a manual task from memory."""
    _active_tasks.discard((job_id, task_name))

def _read_events(job_id: str) -> List[dict]:
    """Read and parse a job's event log from disk. Pure — never writes."""
    file_path = _DATA_DIR / f"{job_id}.jsonl"
    if not file_path.exists():
        return []
    events_list: List[dict] = []
    try:
        with _get_file_lock(job_id):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        try:
                            events_list.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        logger.error(f"Error reading events for job {job_id}: {e}")
    return events_list


def _heal_stuck_events(job_id: str) -> List[dict]:
    """
    Return a job's events, healing tasks orphaned by a server restart.

    A 'started' event with no matching terminal (completed/error) event, whose
    task is not currently registered as active in memory, means the process
    died mid-task — we append one synthetic error event so the UI unblocks.

    This runs at most ONCE per job per process (see `_healed_jobs`): the only
    orphan source is a restart, which the first reconnect catches; tasks that
    fail while the process lives always emit their own terminal event. Repeat
    calls (history polling, extra subscribers) just read.
    """
    events_list = _read_events(job_id)

    with _heal_lock:
        if job_id in _healed_jobs:
            return events_list
        _healed_jobs.add(job_id)

    # Find the last 'started' per agent with no later terminal event.
    pending_starts = {}
    for ev in events_list:
        status = ev.get("status")
        if status == "started":
            pending_starts[ev.get("agent_name")] = ev
        elif status in ("completed", "error"):
            pending_starts.clear()

    _agent_to_task = {"podcast_generator": "podcast", "campaign_generator": "campaign", "qa_agent": "qa"}
    _manual_tasks = {"podcast", "campaign", "video", "qa", "images", "deepeval"}
    stuck_agents = [
        agent for agent in pending_starts
        if _agent_to_task.get(agent, agent) in _manual_tasks
        and (job_id, _agent_to_task.get(agent, agent)) not in _active_tasks
    ]

    if stuck_agents:
        agents_str = ", ".join(stuck_agents)
        healing_event = {
            "job_id": job_id,
            "agent_name": "system",
            "status": "error",
            "message": f"Task(s) [{agents_str}] aborted (server restarted or crashed).",
            "timestamp": time.time(),
            "metrics": {},
        }
        events_list.append(healing_event)
        try:
            with _get_file_lock(job_id):
                with open(_DATA_DIR / f"{job_id}.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(healing_event) + "\n")
            logger.info(f"🩹 Healed stuck manual tasks [{agents_str}] for job {job_id}")
        except Exception as e:
            logger.error(f"Error writing healing event for job {job_id}: {e}")

    return events_list


def _get_file_lock(job_id: str) -> threading.Lock:
    """Get or create a threading lock for a job's event file."""
    if job_id not in _file_locks:
        _file_locks[job_id] = threading.Lock()
    return _file_locks[job_id]


# ============================================================================
# CLEANUP STUBS (Kept for backwards compatibility with api.py)
# ============================================================================

def start_cleanup_task() -> Optional[asyncio.Task]:
    """Captures the main event loop for cross-thread event delivery."""
    global _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
        logger.info("Event bus: captured main event loop for cross-thread delivery.")
    except RuntimeError:
        logger.warning("Event bus: no running loop during startup.")
    return None


def stop_cleanup_task():
    """No-op."""
    pass


# ============================================================================
# CORE EMIT / SUBSCRIBE API
# ============================================================================

def emit(job_id: str, agent_name: str, status: str, message: str, metrics: dict = None):
    """
    Emit an event from an agent node.
    Called synchronously from LangGraph nodes which run in a BackgroundTask thread.
    Uses call_soon_threadsafe to safely bridge back to the main asyncio loop.
    """
    if not job_id:
        return

    event = AgentEvent(
        job_id=job_id,
        agent_name=agent_name,
        status=status,
        message=message,
        timestamp=time.time(),
        metrics=metrics or {},
    )

    event_dict = event.to_dict()

    # Append to JSONL file for persistence (thread-safe via file lock)
    file_path = _DATA_DIR / f"{job_id}.jsonl"
    file_lock = _get_file_lock(job_id)
    try:
        with file_lock:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_dict) + "\n")
    except Exception as e:
        logger.error(f"Failed to persist event to disk: {e}")

    queues = _subscribers.get(job_id, [])
    if not queues:
        return

    def _enqueue_safely():
        for q in queues:
            try:
                q.put_nowait(event_dict)
            except asyncio.QueueFull:
                pass

    # Always use the cached main loop for thread-safe delivery.
    # asyncio.Queue.put_nowait() is NOT thread-safe, so we must
    # use call_soon_threadsafe to schedule it on the event loop.
    loop = _main_loop
    if loop is None:
        # Fallback: try to get the running loop (works if called from async context)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(_enqueue_safely)
    else:
        # Last resort: direct call (only safe if in the same thread as the loop)
        _enqueue_safely()


def subscribe(job_id: str) -> asyncio.Queue:
    """
    Subscribe to events for a job.
    Returns a Queue that will receive future events.
    Also replays any past events (loaded from disk).
    """
    queue = asyncio.Queue(maxsize=500)

    # Replay history from disk with healing for stuck events
    history = _heal_stuck_events(job_id)
    for event in history:
        try:
            queue.put_nowait(event)
        except Exception as e:
            logger.warning(f"Skipping replay event for {job_id}: {e}")

    _subscribers[job_id].append(queue)
    return queue


def unsubscribe(job_id: str, queue: asyncio.Queue):
    """Remove a subscriber queue."""
    if job_id in _subscribers:
        try:
            _subscribers[job_id].remove(queue)
        except ValueError:
            pass
        if not _subscribers[job_id]:
            del _subscribers[job_id]


def clear_job(job_id: str):
    """Immediately clean up all data for a completed/failed job."""
    _subscribers.pop(job_id, None)
    _file_locks.pop(job_id, None)
    with _heal_lock:
        _healed_jobs.discard(job_id)
    file_path = _DATA_DIR / f"{job_id}.jsonl"
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass


def get_history(job_id: str) -> List[dict]:
    """
    Get all stored events for a job from disk.
    """
    return _heal_stuck_events(job_id)
