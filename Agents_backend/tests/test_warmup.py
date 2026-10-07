"""
The pipeline's imports are paid at boot, off the first user's request.

The first POST /api/jobs used to import the whole agents package inside its async
handler (about 3s, measured), blocking the event loop so every WebSocket and every
other request stalled. A boot-time thread now does that work, and a lock makes sure
the warm-up and the first job never execute main.py twice between them.
"""

import asyncio
import threading
from types import SimpleNamespace

from api import background, main as api_main


def test_warmup_loads_the_pipeline(monkeypatch):
    loaded = []
    monkeypatch.setattr(background, "_get_pipeline_main", lambda: loaded.append("main"))

    api_main._warm_imports()

    assert loaded == ["main"]


def test_a_failed_warmup_is_not_fatal(monkeypatch):
    """No OPENAI_API_KEY at boot must not stop the API; the first request reports it."""

    def no_key():
        raise RuntimeError("OPENAI_API_KEY not set")

    monkeypatch.setattr(background, "_get_pipeline_main", no_key)

    api_main._warm_imports()  # returns instead of raising


def _boot(monkeypatch, enabled: bool) -> list:
    """Run the app's lifespan with threading.Thread replaced by a recorder."""
    started = []

    class _Thread:
        def __init__(self, target, name, daemon):
            started.append((target, name, daemon))

        def start(self):
            pass

    monkeypatch.setenv("WARMUP_IMPORTS", "1" if enabled else "0")
    monkeypatch.setattr(api_main, "threading", SimpleNamespace(Thread=_Thread))

    async def run():
        async with api_main.lifespan(api_main.app):
            pass

    asyncio.run(run())
    return started


def test_boot_starts_a_daemon_warmup_thread(monkeypatch):
    assert _boot(monkeypatch, enabled=True) == [(api_main._warm_imports, "warm-imports", True)]


def test_warmup_can_be_switched_off(monkeypatch):
    assert _boot(monkeypatch, enabled=False) == []


def test_two_callers_execute_main_py_only_once(monkeypatch):
    """The warm-up and the first job can overlap. Half-way through exec_module the module
    is in sys.modules without save_blog_content, so an unlocked second caller ran
    main.py a second time. Both callers below must get the same module object."""
    import sys

    executions = []
    inside = threading.Event()
    release = threading.Event()

    class _Loader:
        def exec_module(self, module):
            executions.append(module)
            inside.set()
            release.wait(5)  # hold the first caller mid-import
            module.save_blog_content = lambda: None

    fake_spec = SimpleNamespace(loader=_Loader())
    import importlib.util

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: fake_spec)
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda spec: SimpleNamespace())
    monkeypatch.delitem(sys.modules, "backend_pipeline_main", raising=False)

    got = []
    first = threading.Thread(target=lambda: got.append(background._get_pipeline_main()))
    first.start()
    assert inside.wait(5), "the first caller never reached exec_module"

    second = threading.Thread(target=lambda: got.append(background._get_pipeline_main()))
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    sys.modules.pop("backend_pipeline_main", None)

    assert len(executions) == 1, "main.py was executed twice"
    assert len(got) == 2 and got[0] is got[1]
