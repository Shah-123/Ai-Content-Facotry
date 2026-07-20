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

def register_active_task(job_id: str, task_name: str):
    """Register a manual task as currently running in memory."""
    _active_tasks.add((job_id, task_name))

def unregister_active_task(job_id: str, task_name: str):
    """Unregister a manual task from memory."""
    _active_tasks.discard((job_id, task_name))

def _heal_stuck_events(job_id: str) -> List[dict]:
    """
    Read events from disk, check for stuck/orphaned manual tasks,
    write a recovery event if needed, and return the list of events.
    """
    file_path = _DATA_DIR / f"{job_id}.jsonl"
    file_lock = _get_file_lock(job_id)
    events_list = []
    
    if not file_path.exists():
        return events_list

    try:
        with file_lock:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            for line in lines:
                stripped = line.strip()
                if stripped:
                    try:
                        events_list.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass
                        
            # Analyze event sequence to find orphaned tasks
            pending_starts = {}
            for idx, ev in enumerate(events_list):
                status = ev.get("status")
                agent = ev.get("agent_name")
                if status == "started":
                    pending_starts[agent] = ev
                elif status in ("completed", "error"):
                    pending_starts.clear()
            
            # If there are pending starts, check if they are still active
            stuck_agents = []
            for agent, start_ev in pending_starts.items():
                task_name = agent
                if agent == "podcast_generator":
                    task_name = "podcast"
                elif agent == "campaign_generator":
                    task_name = "campaign"
                elif agent == "qa_agent":
                    task_name = "qa"
                
                # Check if it is a manual task
                if task_name in {"podcast", "campaign", "video", "qa", "images", "deepeval"}:
                    # Check if it is currently registered as active in memory
                    if (job_id, task_name) not in _active_tasks:
                        stuck_agents.append(agent)
            
            if stuck_agents:
                # We have stuck tasks! Write a system error event to heal them.
                agents_str = ", ".join(stuck_agents)
                healing_event = {
                    "job_id": job_id,
                    "agent_name": "system",
                    "status": "error",
                    "message": f"Task(s) [{agents_str}] aborted (server restarted or crashed).",
                    "timestamp": time.time(),
                    "metrics": {}
                }
                events_list.append(healing_event)
                
                # Persist the healing event to disk
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(healing_event) + "\n")
                    
                logger.info(f"🩹 Healed stuck manual tasks [{agents_str}] for job {job_id}")
                
    except Exception as e:
        logger.error(f"Error healing stuck events for job {job_id}: {e}")
        
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
