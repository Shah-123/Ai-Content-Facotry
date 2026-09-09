"""
WebSocket lifecycle: the server must notice when a client goes away.

The endpoint only ever SENDS. A disconnect, however, is delivered on the
RECEIVE channel, so unless something drains receive() the server never observes
the close: it keeps writing 30-second keepalives into a dead transport
indefinitely, uvicorn logs "socket.send() raised exception" for each one, and
the subscriber queue is never released. Closing a browser tab leaked a
connection permanently, and the log filled with send errors during a demo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ws.db")
    db.init_db()
    from api.main import app

    with TestClient(app) as c:
        yield c


def test_subscription_is_released_on_close(client):
    """The queue must not outlive the connection.

    NOTE: this passes with or without the receive-channel drain, because
    TestClient cancels the server task on context exit, which reaches the
    `finally`. The real leak needs a live uvicorn socket, so the mechanism
    itself is covered by the two `_await_disconnect` tests below. This one
    guards the cleanup path in `finally`.
    """
    import event_bus

    job = "ws-lifecycle-job"
    assert job not in event_bus._subscribers

    with client.websocket_connect(f"/ws/{job}") as ws:
        event_bus.emit(job, "router", "started", "hello")
        assert ws.receive_json()["message"] == "hello"
        assert len(event_bus._subscribers[job]) == 1

    assert event_bus._subscribers.get(job, []) == []


class TestDisconnectDetection:
    """The mechanism that makes the server notice a departed client.

    Exercised directly rather than through TestClient: TestClient cancels the
    server task on teardown, so a send-only handler appears to clean up
    correctly there while leaking against a real uvicorn socket.
    """

    def test_await_disconnect_returns_on_the_disconnect_message(self):
        import asyncio
        from api.routes.websocket import _await_disconnect

        class FakeWS:
            def __init__(self):
                self.messages = [
                    {"type": "websocket.receive", "text": "ignored"},
                    {"type": "websocket.disconnect", "code": 1001},
                ]

            async def receive(self):
                return self.messages.pop(0)

        # Returns rather than hanging: this is what ends the send loop.
        asyncio.run(asyncio.wait_for(_await_disconnect(FakeWS()), timeout=2))

    def test_await_disconnect_returns_when_receive_raises(self):
        """A dropped transport raises rather than yielding a message."""
        import asyncio
        from starlette.websockets import WebSocketDisconnect
        from api.routes.websocket import _await_disconnect

        class BrokenWS:
            async def receive(self):
                raise WebSocketDisconnect(code=1006)

        asyncio.run(asyncio.wait_for(_await_disconnect(BrokenWS()), timeout=2))

    def test_send_refuses_once_the_socket_is_not_connected(self):
        """No frame may be written to a socket that is not CONNECTED.

        Every such write is a `socket.send() raised exception` line in the
        server log during a demo.
        """
        import asyncio
        from starlette.websockets import WebSocketState
        from api.routes.websocket import _send

        class ClosedWS:
            application_state = WebSocketState.DISCONNECTED
            sent = False

            async def send_json(self, _payload):
                ClosedWS.sent = True

        assert asyncio.run(_send(ClosedWS(), {"type": "ping"})) is False
        assert ClosedWS.sent is False, "wrote to a disconnected socket"

    def test_send_reports_failure_instead_of_raising(self):
        import asyncio
        from starlette.websockets import WebSocketState
        from api.routes.websocket import _send

        class FailingWS:
            application_state = WebSocketState.CONNECTED

            async def send_json(self, _payload):
                raise RuntimeError("transport gone")

        assert asyncio.run(_send(FailingWS(), {"a": 1})) is False


def test_replayed_history_does_not_close_the_socket(client):
    """A historical system/completed must not terminate a fresh connection.

    Reconnecting to a finished job should still deliver its backlog; only a
    LIVE terminal event should close the stream.
    """
    import event_bus

    job = "ws-replay-job"
    event_bus.emit(job, "router", "started", "first")
    event_bus.emit(job, "system", "completed", "done")

    with client.websocket_connect(f"/ws/{job}") as ws:
        assert ws.receive_json()["message"] == "first"
        assert ws.receive_json()["message"] == "done"
        # Still open: a new live event must arrive.
        event_bus.emit(job, "writer", "working", "after replay")
        assert ws.receive_json()["message"] == "after replay"

    event_bus.clear_job(job)


def test_live_terminal_event_closes_the_stream(client):
    """A live system/completed should end the connection, not linger."""
    import event_bus
    from starlette.websockets import WebSocketDisconnect

    job = "ws-terminal-job"
    with client.websocket_connect(f"/ws/{job}") as ws:
        event_bus.emit(job, "system", "completed", "finished")
        assert ws.receive_json()["message"] == "finished"
        with pytest.raises(WebSocketDisconnect):
            # The server closes shortly after the terminal event.
            for _ in range(5):
                ws.receive_json()

    event_bus.clear_job(job)


def test_endpoint_drains_the_receive_channel(client):
    """Source guard: without a receive() drain the disconnect is invisible."""
    import inspect
    from api.routes import websocket as ws_module

    src = inspect.getsource(ws_module)
    assert "_await_disconnect" in src
    assert "websocket.receive()" in src, (
        "nothing drains the receive channel; a client disconnect would go "
        "unnoticed and keepalives would be written to a dead socket forever"
    )


def test_auth_rejects_before_accepting(client, monkeypatch):
    """A bad key must be refused without ever subscribing."""
    import event_bus
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setenv("API_KEY", "ws-secret")
    job = "ws-auth-job"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{job}?api_key=wrong") as ws:
            ws.receive_json()
    assert event_bus._subscribers.get(job, []) == []
