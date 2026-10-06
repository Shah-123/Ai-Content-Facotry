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

    # A disconnect is delivered on the RECEIVE channel. This endpoint only ever
    # sends, so without something draining receive() the server never learns the
    # client has gone: it keeps writing keepalives into a dead transport every
    # 30 seconds forever, uvicorn logs "socket.send() raised exception" on each
    # one, and the subscriber queue is never released. Closing a browser tab was
    # enough to leak a connection permanently.
    disconnected = asyncio.create_task(_await_disconnect(websocket))

    try:
        while not disconnected.done():
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {getter, disconnected},
                timeout=30.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if disconnected in done:
                getter.cancel()
                break

            if getter in done:
                event = getter.result()
                is_replay = replay_remaining > 0
                if is_replay:
                    replay_remaining -= 1

                if not await _send(websocket, event):
                    break

                # Only close on LIVE (non-replayed) terminal events
                if not is_replay and (
                    event.get("status") == "error"
                    or (event.get("agent_name") == "system"
                        and event.get("status") == "completed")
                ):
                    await asyncio.sleep(0.5)
                    break
            else:
                # Idle for 30s — keepalive
                getter.cancel()
                if not await _send(websocket, {"type": "ping"}):
                    break
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected for job {job_id}")
    finally:
        disconnected.cancel()
        events.unsubscribe(job_id, queue)
        try:
            from starlette.websockets import WebSocketState
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1000)
        except Exception:
            pass


async def _await_disconnect(websocket: WebSocket) -> None:
    """Resolve as soon as the client goes away.

    `receive()` yields a `websocket.disconnect` message on close and raises
    `WebSocketDisconnect` thereafter. Draining it is the only way the server
    observes a closed connection; incoming frames are not otherwise used.
    """
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
    except Exception:
        return


async def _send(websocket: WebSocket, payload: dict) -> bool:
    """Send one JSON frame. Returns False once the socket is unusable."""
    from starlette.websockets import WebSocketState

    if websocket.application_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        return False
