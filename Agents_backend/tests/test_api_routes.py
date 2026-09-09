"""
Static safety guards for the FastAPI route layer.

These are AST checks rather than request tests: they are fast, need no server,
no database and no API keys, and they catch the specific class of mistake that
is invisible in review and in manual testing — a synchronous database or
filesystem call sitting inside an `async def` handler.

WHY IT MATTERS
--------------
FastAPI runs `async def` handlers directly on the event loop. A blocking call
there stalls *every* concurrent request, including the WebSocket that streams
agent progress to the dashboard during generation. Handlers that cannot avoid
blocking work must hand it to a worker thread with `asyncio.to_thread`, which
most of this router already did — five handlers did not, and `serve_file` ran a
full self-healing pass (directory glob, stat of every registered artefact, and
potentially a DB write) on every single image the browser fetched.
"""

from __future__ import annotations

import ast
import pathlib

_ROUTES_DIR = pathlib.Path(__file__).resolve().parent.parent / "api" / "routes"

# Functions that hit SQLite or walk the filesystem. Safe in a worker thread,
# never safe directly inside an `async def`.
_BLOCKING_CALLS = {
    "get_job",
    "get_job_healed",
    "list_jobs",
    "list_jobs_healed",
    "update_job",
    "create_job",
    "delete_job",
    "_heal_stuck_events",
    "_verify_and_clean_job_files",
}


def _async_defs(path: pathlib.Path) -> list[ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def _direct_blocking_calls(fn: ast.AsyncFunctionDef) -> list[tuple[str, int]]:
    """Blocking functions *invoked* inside `fn`.

    `asyncio.to_thread(get_job, job_id)` passes `get_job` as a bare Name, not a
    Call, so correctly-threaded usage is not reported. Only a real invocation —
    `get_job(job_id)` — produces a Call node with that name.
    """
    return [
        (node.func.id, node.lineno)
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _BLOCKING_CALLS
    ]


def test_no_async_route_blocks_the_event_loop():
    offenders: list[str] = []
    checked = 0
    for path in sorted(_ROUTES_DIR.glob("*.py")):
        for fn in _async_defs(path):
            checked += 1
            for name, line in _direct_blocking_calls(fn):
                offenders.append(
                    f"{path.name}:{line} — {fn.name}() calls {name}() directly; "
                    f"wrap it in `await asyncio.to_thread({name}, ...)`"
                )

    assert checked > 0, "no async handlers found — did the routes package move?"
    assert not offenders, "blocking calls on the event loop:\n  " + "\n  ".join(offenders)


def test_serve_file_does_not_run_the_self_healer():
    """The hot path for every `<img src>` must stay cheap.

    `get_job_healed` globs the images directory, stats every registered artefact
    and may write to the database. Serving one static file needs `blog_folder`
    and nothing else.
    """
    path = _ROUTES_DIR / "jobs.py"
    fn = next(f for f in _async_defs(path) if f.name == "serve_file")
    called = {
        n.func.id for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    names = {
        n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
    }
    assert "get_job_healed" not in names, (
        "serve_file must use get_job, not get_job_healed — healing on every "
        "asset fetch is what made image-heavy pages stall the event loop"
    )
    assert "get_job" in names


def test_serve_file_keeps_its_path_containment_check():
    """Guard the traversal fix: a prefix check is not a containment check."""
    src = (_ROUTES_DIR / "jobs.py").read_text(encoding="utf-8")
    fn_src = src[src.index("async def serve_file"):]
    fn_src = fn_src[: fn_src.index("@router")] if "@router" in fn_src else fn_src
    assert "is_relative_to" in fn_src, (
        "serve_file lost its containment check — `startswith` would let "
        "blogs/topic_123 read blogs/topic_1234 via ../"
    )
