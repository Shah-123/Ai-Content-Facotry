import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import event_bus as events
from api.auth import api_key_is_valid

logger = logging.getLogger("api.routes.websocket")
router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str, api_key: str | None = None):
    """Stream agent events to the browser in real-time.

    Auth is checked here rather than via a router dependency because the browser
    WebSocket API cannot set headers — the key arrives as `?api_key=`. No-op
    unless API_KEY is configured.
    """
    if not api_key_is_valid(api_key):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    queue = events.subscribe(job_id)

    # Count how many events were pre-loaded (replayed from disk history).
    # We must NOT close the WebSocket when replaying a historical
    # "system:completed" event — only close on a LIVE one.
    replay_remaining = queue.qsize()

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                is_replay = replay_remaining > 0
                if is_replay:
                    replay_remaining -= 1

                try:
                    await websocket.send_json(event)
                except Exception:
                    # Connection closed or error sending
                    break

                # Only close on LIVE (non-replayed) terminal events
                if not is_replay:
                    if event.get("status") == "error" or (
                        event.get("agent_name") == "system"
                        and event.get("status") == "completed"
                    ):
                        await asyncio.sleep(0.5)
                        break
            except asyncio.TimeoutError:
                # Send a keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected for job {job_id}")
    finally:
        events.unsubscribe(job_id, queue)
        try:
            from starlette.websockets import WebSocketState
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1000)
        except Exception:
            pass
