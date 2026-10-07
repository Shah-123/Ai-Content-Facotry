"""
Request-level tests for the FastAPI route layer.

These drive the real application through TestClient against a throwaway SQLite
file. Exactly three things are stubbed and nothing else:

  * `evaluate_topic` — otherwise every job creation costs a live LLM call.
  * `predict_route`  — job creation asks the router beside the guard; the
                       fixture answers None, which means "the pipeline asks".
  * `_run_pipeline`  — TestClient executes BackgroundTasks after the response
                       returns, so an unstubbed test would launch the entire
                       generation pipeline in a worker thread.

Routing, validation, auth, persistence and path containment are all exercised
for real. Static (AST) guards on the same router live in test_api_routes.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App wired to a temporary database, with the pipeline stubbed out."""
    import db

    # get_db() reads DB_PATH at connect time, so redirecting it here is enough —
    # but the tables live in the real file, so recreate them in the temp one.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_jobs.db")
    db.init_db()
    # Pin the token-signing secret: it falls back to API_KEY, so tests that
    # set API_KEY would otherwise invalidate the session minted below.
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret")
    from api import users
    users.init_users()

    import api.routes.jobs as jobs_routes

    from Graph.agents import routing

    monkeypatch.setattr(routing, "predict_route", lambda _topic: None)

    dispatched: list[dict] = []
    monkeypatch.setattr(jobs_routes, "_run_pipeline", lambda **kw: dispatched.append(kw))

    from api.main import app

    with TestClient(app) as c:
        # Every jobs route requires a signed-in owner; sign one up and send its
        # bearer token by default. Ownership tests build their own clients.
        signup = c.post("/api/auth/signup", json={"email": "owner@example.test", "password": "test-password-1"})
        c.headers["Authorization"] = f"Bearer {signup.json()['token']}"
        c.user_id = signup.json()["user"]["id"]  # type: ignore[attr-defined]
        c.dispatched = dispatched  # type: ignore[attr-defined]
        yield c


def _stub_topic_guard(monkeypatch, *, safe=True, category="ok"):
    """Replace the LLM safety check with a fixed verdict."""
    from Graph.agents import topic_guard

    verdict = topic_guard.TopicGuardVerdict(
        is_safe=safe,
        category=category,
        reason="stubbed verdict",
        suggested_topic="" if safe else "A safer topic",
    )
    monkeypatch.setattr(topic_guard, "evaluate_topic", lambda _topic: verdict)
    return verdict


# ---------------------------------------------------------------------------


class TestJobLifecycle:
    def test_list_jobs_is_empty_on_a_fresh_database(self, client):
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert r.json() == []

    def test_unknown_job_returns_404(self, client):
        assert client.get("/api/jobs/does-not-exist").status_code == 404

    def test_creating_a_job_persists_it_and_dispatches_the_pipeline(self, client, monkeypatch):
        _stub_topic_guard(monkeypatch)
        r = client.post("/api/jobs", json={"topic": "How photosynthesis works"})
        assert r.status_code == 200, r.text

        job = r.json()
        assert job["topic"] == "How photosynthesis works"
        assert job["status"] == "pending"

        assert client.get(f"/api/jobs/{job['id']}").status_code == 200
        assert len(client.get("/api/jobs").json()) == 1

        assert len(client.dispatched) == 1
        assert client.dispatched[0]["job_id"] == job["id"]

    def test_config_round_trips_through_the_database(self, client, monkeypatch):
        """GenerationConfig is the durable record of a run's inputs."""
        _stub_topic_guard(monkeypatch)
        r = client.post(
            "/api/jobs",
            json={
                "topic": "Test topic for config",
                "tone": "technical",
                "sections": 5,
                "keywords": ["alpha", "beta"],
                "generate_podcast": True,
            },
        )
        cfg = client.get(f"/api/jobs/{r.json()['id']}").json()["config"]
        assert cfg["tone"] == "technical"
        assert cfg["sections"] == 5
        assert cfg["keywords"] == ["alpha", "beta"]
        assert cfg["generate_podcast"] is True

    def test_deleting_a_job_removes_it(self, client, monkeypatch):
        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Topic to delete"}).json()["id"]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 200
        assert client.get(f"/api/jobs/{job_id}").status_code == 404

    def test_deleting_an_unknown_job_is_404_not_500(self, client):
        assert client.delete("/api/jobs/nope").status_code == 404


class TestRouterRunsBesideTheGuard:
    """The router's answer depends only on the topic, so job creation starts asking it
    beside the topic guard, and hands the call to the pipeline, which waits for what is
    left of it. The HTTP response never waits for the router."""

    def test_the_call_in_flight_is_handed_to_the_pipeline(self, client, monkeypatch):
        from Graph.agents import routing
        from Graph.state import RouterDecision

        decision = RouterDecision(needs_research=True, mode="hybrid", reason="r", queries=["q"])
        monkeypatch.setattr(routing, "predict_route", lambda _topic: decision)
        _stub_topic_guard(monkeypatch)

        assert client.post("/api/jobs", json={"topic": "How photosynthesis works"}).status_code == 200

        assert client.dispatched[0]["router_future"].result(timeout=5) == decision
        assert isinstance(client.dispatched[0]["usage_before"], dict)

    def test_job_creation_does_not_wait_for_the_router(self, client, monkeypatch):
        """A slow router must not delay the job appearing: before this change the router
        ran inside the pipeline, so the response came back as soon as the guard did."""
        import threading
        import time

        from Graph.agents import routing

        release = threading.Event()
        monkeypatch.setattr(routing, "predict_route", lambda _topic: release.wait(10))
        _stub_topic_guard(monkeypatch)

        started = time.perf_counter()
        r = client.post("/api/jobs", json={"topic": "How photosynthesis works"})
        elapsed = time.perf_counter() - started
        still_running = not client.dispatched[0]["router_future"].done()
        release.set()

        assert r.status_code == 200
        assert elapsed < 5, "the response waited for the router"
        assert still_running

    def test_the_guard_and_the_router_are_in_flight_together(self, client, monkeypatch):
        """Each waits on one barrier, which only opens if both are running at once."""
        import threading

        from Graph.agents import routing, topic_guard

        verdict = _stub_topic_guard(monkeypatch)
        barrier = threading.Barrier(2, timeout=5)

        def guard(_topic):
            barrier.wait()
            return verdict

        def route(_topic):
            barrier.wait()

        monkeypatch.setattr(topic_guard, "evaluate_topic", guard)
        monkeypatch.setattr(routing, "predict_route", route)

        assert client.post("/api/jobs", json={"topic": "How photosynthesis works"}).status_code == 200

    def test_a_rejection_does_not_wait_for_the_router(self, client, monkeypatch):
        import threading
        import time

        from Graph.agents import routing

        release = threading.Event()
        monkeypatch.setattr(routing, "predict_route", lambda _topic: release.wait(10))
        _stub_topic_guard(monkeypatch, safe=False, category="nonsense")

        started = time.perf_counter()
        r = client.post("/api/jobs", json={"topic": "something unsafe"})
        elapsed = time.perf_counter() - started
        release.set()

        assert r.status_code == 400
        assert elapsed < 5, "the rejection waited for the speculative router call"

    def test_junk_the_free_screen_rejects_gets_no_router_call(self, client, monkeypatch):
        from Graph.agents import routing

        asked = []
        monkeypatch.setattr(routing, "predict_route", lambda topic: asked.append(topic))

        assert client.post("/api/jobs", json={"topic": "asdfgh"}).status_code == 400
        assert asked == []

    def test_the_pipeline_accepts_what_the_handler_passes(self):
        """_run_pipeline is stubbed everywhere above, so a drifted signature would go unnoticed."""
        import inspect

        from api import background

        params = inspect.signature(background._run_pipeline).parameters
        for name in ("job_id", "topic", "config", "worker_event", "router_future", "usage_before"):
            assert name in params, name

    def test_the_pipeline_starts_with_the_answer_to_the_call_already_in_flight(self, monkeypatch, tmp_path):
        """Drive the real _run_pipeline with a recording graph: the decision the API's call
        produced must reach the graph's initial state, where router_node picks it up."""
        import sqlite3
        import threading
        from concurrent.futures import Future
        from types import SimpleNamespace

        from api import background
        from Graph.state import RouterDecision

        decision = RouterDecision(needs_research=True, mode="hybrid", reason="r", queries=["q"])
        asked = Future()
        asked.set_result(decision)

        started_with = []

        class _Graph:
            def get_state(self, _cfg):
                return SimpleNamespace(next=(), values={})

            def stream(self, state, _cfg, **_kw):
                started_with.append(state)
                return iter(())

        fake_main = SimpleNamespace(
            build_graph=lambda memory: _Graph(),
            create_blog_structure=lambda topic: {k: str(tmp_path) for k in ("base", "reports", "metadata")},
            save_blog_content=lambda folders, state: {},
            generate_readme=lambda *a: None,
            refine_plan_with_llm=None,
        )
        monkeypatch.setattr(background, "_get_pipeline_main", lambda: fake_main)
        monkeypatch.setattr(background, "_create_sqlite_checkpoint_conn",
                            lambda _path: sqlite3.connect(":memory:", check_same_thread=False))
        monkeypatch.setattr(background.events, "emit", lambda *a, **k: None)
        for name in ("set_job_running", "set_job_awaiting_approval", "set_job_completed",
                     "set_job_failed", "update_job"):
            monkeypatch.setattr(background, name, lambda *a, **k: None)
        monkeypatch.setattr(background, "get_job_healed", lambda _job_id: None)
        monkeypatch.setattr(background, "_update_metadata_json", lambda *a, **k: None)

        background._run_pipeline(job_id="j", topic="t", config={}, worker_event=threading.Event(),
                                 router_future=asked)

        assert started_with[0]["router_decision"] == decision.model_dump()


class TestTopicGuardGatesJobCreation:
    """A rejected topic must reach neither the pipeline nor the database.

    The guard runs before create_job precisely so an unsafe submission costs
    nothing. If a row were written anyway, that claim would be false and the
    job list would accumulate rejected topics.
    """

    def test_unsafe_topic_is_rejected_with_a_structured_reason(self, client, monkeypatch):
        _stub_topic_guard(monkeypatch, safe=False, category="self_harm")
        r = client.post("/api/jobs", json={"topic": "something unsafe"})
        assert r.status_code == 400

        detail = r.json()["detail"]
        assert detail["error"] == "topic_rejected"
        assert detail["category"] == "self_harm"
        assert detail["suggested_topic"] == "A safer topic"

    def test_rejected_topic_creates_no_job_and_spends_nothing(self, client, monkeypatch):
        _stub_topic_guard(monkeypatch, safe=False, category="nonsense")
        client.post("/api/jobs", json={"topic": "asdfgh"})
        assert client.get("/api/jobs").json() == []
        assert client.dispatched == []

    def test_missing_topic_is_a_validation_error(self, client):
        assert client.post("/api/jobs", json={"tone": "professional"}).status_code == 422


class TestApiKeyGate:
    """API_KEY is a no-op when unset and mandatory when set."""

    def test_open_when_unset(self, client, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        assert client.get("/api/jobs").status_code == 200

    def test_rejects_missing_key_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "s3cret-for-test")
        assert client.get("/api/jobs").status_code == 401

    def test_accepts_the_correct_header(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "s3cret-for-test")
        assert client.get("/api/jobs", headers={"X-API-Key": "s3cret-for-test"}).status_code == 200

    def test_rejects_a_wrong_key(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY", "s3cret-for-test")
        assert client.get("/api/jobs", headers={"X-API-Key": "wrong"}).status_code == 401

    def test_accepts_the_query_param_fallback(self, client, monkeypatch):
        """Browsers cannot set headers on <img src> or download links."""
        monkeypatch.setenv("API_KEY", "s3cret-for-test")
        assert client.get("/api/jobs?api_key=s3cret-for-test").status_code == 200


class TestFileServingContainment:
    def test_unknown_job_is_404(self, client):
        assert client.get("/api/files/nope/blog.md").status_code == 404

    def test_traversal_outside_the_job_folder_is_refused(self, client, monkeypatch, tmp_path):
        """Containment must hold regardless of how the URL is normalised."""
        import db

        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Containment test"}).json()["id"]

        job_folder = tmp_path / "blogs" / "job_folder"
        (job_folder / "content").mkdir(parents=True)
        (job_folder / "content" / "ok.md").write_text("inside", encoding="utf-8")
        (tmp_path / "blogs" / "secret.txt").write_text("SHOULD NOT BE SERVED", encoding="utf-8")
        db.update_job(job_id, blog_folder=str(job_folder))

        good = client.get(f"/api/files/{job_id}/content/ok.md")
        assert good.status_code == 200
        assert good.text == "inside"

        for attempt in ("../secret.txt", "..%2Fsecret.txt", "content/../../secret.txt"):
            r = client.get(f"/api/files/{job_id}/{attempt}")
            assert r.status_code in (403, 404), f"{attempt} -> {r.status_code}"
            assert "SHOULD NOT BE SERVED" not in r.text

    def test_sibling_folder_sharing_a_name_prefix_is_refused(
        self, client, monkeypatch, tmp_path
    ):
        """The specific flaw `is_relative_to` exists to fix.

        A prefix test (`str(target).startswith(str(base))`) passes for a SIBLING
        directory whose name merely begins with the job folder's name — the
        `blogs/topic_123` vs `blogs/topic_1234` case named in the source comment.
        Plain `../` escapes are caught by either check, so a test using only
        those would still pass against the vulnerable version and prove nothing.

        The segments must be PERCENT-ENCODED. httpx resolves a literal `../` out
        of the URL before the request is sent, so the raw form never reaches the
        handler and silently tests nothing; `..%2F` survives and arrives as a
        genuine traversal.
        """
        import db

        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Prefix test"}).json()["id"]

        blogs = tmp_path / "prefix_blogs"
        job_folder = blogs / "topic_123"
        job_folder.mkdir(parents=True)
        # Sibling whose name has the job folder's name as a strict prefix.
        sibling = blogs / "topic_1234"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("ANOTHER JOB'S DATA", encoding="utf-8")
        db.update_job(job_id, blog_folder=str(job_folder))

        r = client.get(f"/api/files/{job_id}/..%2Ftopic_1234%2Fsecret.txt")
        assert r.status_code in (403, 404), (
            f"served another job's file (status {r.status_code}) — the "
            f"containment check has regressed to a prefix comparison"
        )
        assert "ANOTHER JOB'S DATA" not in r.text


class TestHumanInTheLoopEndpoints:
    """The approve / revise / edit handoff — the most stateful path in the API."""

    def test_all_hitl_endpoints_404_on_an_unknown_job(self, client):
        assert client.get("/api/jobs/nope/approve-plan").status_code == 404
        assert client.post("/api/jobs/nope/revise-plan", json={"feedback": "x"}).status_code == 404
        assert client.post(
            "/api/jobs/nope/update-plan", json={"blog_title": "T", "tasks": []}
        ).status_code == 404

    def test_approve_marks_the_job_running(self, client, monkeypatch):
        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Approve me"}).json()["id"]

        assert client.get(f"/api/jobs/{job_id}/approve-plan").json() == {"status": "approved"}
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"

    def test_revision_feedback_is_queued_for_the_worker(self, client, monkeypatch):
        from api.state import _plan_revisions

        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Revise me"}).json()["id"]

        r = client.post(
            f"/api/jobs/{job_id}/revise-plan", json={"feedback": "make section 2 shorter"}
        )
        assert r.json() == {"status": "revision_queued"}
        assert _plan_revisions[job_id] == "make section 2 shorter"

    def test_direct_plan_edit_renumbers_tasks_and_updates_tone(self, client, monkeypatch):
        """Task ids must be re-sequenced: merge_content orders sections by id."""
        from api.state import _direct_plan_updates

        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Edit me"}).json()["id"]

        r = client.post(
            f"/api/jobs/{job_id}/update-plan",
            json={
                "blog_title": "A Directly Edited Title",
                "tone": "conversational",
                "tasks": [
                    {"title": "Second", "goal": "g2", "bullets": ["b"], "target_words": 400},
                    {"title": "First", "goal": "g1", "bullets": ["b"]},
                ],
            },
        )
        assert r.json() == {"status": "plan_updated", "sections": 2}

        plan = _direct_plan_updates[job_id]
        assert plan.blog_title == "A Directly Edited Title"
        assert [t.id for t in plan.tasks] == [0, 1]
        assert [t.title for t in plan.tasks] == ["Second", "First"]
        assert plan.tasks[1].target_words == 350  # schema default applied
        assert client.get(f"/api/jobs/{job_id}").json()["config"]["tone"] == "conversational"


class TestUploadValidation:
    def test_unsupported_extension_is_rejected_before_parsing(self, client):
        r = client.post(
            "/api/uploads",
            files={"file": ("payload.exe", b"MZ\x00\x00", "application/octet-stream")},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "unsupported_format"

    def test_upload_id_with_traversal_characters_is_rejected(self, client):
        assert client.get("/api/uploads/..%2F..%2Fetc").status_code in (400, 404)


class TestSaveEditedArticle:
    """PUT /api/jobs/{id}/blog must update BOTH copies of the article: the job
    row (UI, /blog, exports) and the Markdown file (manual tasks)."""

    def _finished_job(self, client, tmp_path, status="completed"):
        import db

        folder = tmp_path / "blog"
        (folder / "content").mkdir(parents=True)
        md = folder / "content" / "edit_me.md"
        md.write_text("# Old\n\nold text", encoding="utf-8")
        job = db.create_job(topic="Edit me", owner_id=client.user_id)
        db.update_job(job["id"], status=status, blog_folder=str(folder),
                      final_content="# Old\n\nold text")
        return job["id"], md

    def test_save_updates_the_row_the_file_and_the_exports(self, client, tmp_path):
        job_id, md = self._finished_job(client, tmp_path)

        r = client.put(f"/api/jobs/{job_id}/blog", json={"content": "# New\n\nedited words here"})

        assert r.status_code == 200
        assert r.json() == {"word_count": 5}
        assert client.get(f"/api/jobs/{job_id}/blog").json()["content"] == "# New\n\nedited words here"
        assert md.read_text(encoding="utf-8") == "# New\n\nedited words here"   # manual tasks read this
        html = client.get(f"/api/jobs/{job_id}/export/html").text
        assert "edited words here" in html and "old text" not in html

    def test_refuses_while_the_job_is_running(self, client, tmp_path):
        """The pipeline or a manual task would overwrite the edit when it finishes."""
        job_id, md = self._finished_job(client, tmp_path, status="running")

        r = client.put(f"/api/jobs/{job_id}/blog", json={"content": "edited"})

        assert r.status_code == 409
        assert md.read_text(encoding="utf-8") == "# Old\n\nold text"

    def test_unknown_job_is_404_and_empty_content_is_rejected(self, client, tmp_path):
        assert client.put("/api/jobs/nope/blog", json={"content": "x"}).status_code == 404
        job_id, _ = self._finished_job(client, tmp_path)
        assert client.put(f"/api/jobs/{job_id}/blog", json={"content": ""}).status_code == 422


class TestJobOwnership:
    """Each account sees and touches only its own jobs (Known Limitation removed:
    'any authenticated caller can read and delete every job')."""

    def _second_user(self, client) -> dict:
        r = client.post("/api/auth/signup", json={"email": "intruder@example.test", "password": "test-password-2"},
                        headers={"Authorization": ""})
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def _owned_job(self, client, monkeypatch, tmp_path) -> str:
        import db
        _stub_topic_guard(monkeypatch)
        job_id = client.post("/api/jobs", json={"topic": "Private job"}).json()["id"]
        folder = tmp_path / "private"
        (folder / "content").mkdir(parents=True)
        (folder / "content" / "a.md").write_text("private text", encoding="utf-8")
        db.update_job(job_id, status="completed", blog_folder=str(folder), final_content="private text")
        return job_id

    def test_another_account_cannot_see_or_touch_the_job(self, client, monkeypatch, tmp_path):
        job_id = self._owned_job(client, monkeypatch, tmp_path)
        other = self._second_user(client)

        assert client.get("/api/jobs", headers=other).json() == []
        for method, path, body in [
            ("get", f"/api/jobs/{job_id}", None),
            ("get", f"/api/jobs/{job_id}/blog", None),
            ("put", f"/api/jobs/{job_id}/blog", {"content": "overwritten"}),
            ("get", f"/api/jobs/{job_id}/export/html", None),
            ("get", f"/api/files/{job_id}/content/a.md", None),
            ("post", f"/api/jobs/{job_id}/generate-video", None),
            ("get", f"/api/jobs/{job_id}/approve-plan", None),
            ("delete", f"/api/jobs/{job_id}", None),
        ]:
            r = client.request(method.upper(), path, json=body, headers=other)
            assert r.status_code == 404, f"{method.upper()} {path} -> {r.status_code}"

        # The owner still has it, untouched.
        assert [j["id"] for j in client.get("/api/jobs").json()] == [job_id]
        assert client.get(f"/api/jobs/{job_id}/blog").json()["content"] == "private text"

    def test_signed_out_requests_are_refused(self, client):
        anonymous = {"Authorization": ""}
        client.cookies.clear()
        assert client.get("/api/jobs", headers=anonymous).status_code == 401
        assert client.get("/api/jobs/anything", headers=anonymous).status_code == 401

    def test_the_session_cookie_alone_authenticates_with_a_csrf_header(self, client, monkeypatch, tmp_path):
        """<img>, downloads and the WebSocket carry only the cookie."""
        job_id = self._owned_job(client, monkeypatch, tmp_path)
        del client.headers["Authorization"]          # cookie from signup only

        assert client.get(f"/api/files/{job_id}/content/a.md").text == "private text"
        # State change via cookie without X-Requested-With: refused (CSRF).
        assert client.put(f"/api/jobs/{job_id}/blog", json={"content": "x"}).status_code == 403
        r = client.put(f"/api/jobs/{job_id}/blog", json={"content": "edited"},
                       headers={"X-Requested-With": "fetch"})
        assert r.status_code == 200

    def test_logout_clears_the_cookie(self, client):
        del client.headers["Authorization"]
        assert client.get("/api/jobs").status_code == 200
        client.post("/api/auth/logout", headers={"X-Requested-With": "fetch"})
        assert client.get("/api/jobs").status_code == 401

    def test_ownerless_jobs_go_to_the_only_account_and_never_to_a_second(self, client):
        import db
        from api import users

        legacy = db.create_job(topic="Before accounts existed")["id"]
        assert users.claim_ownerless_jobs() == 1
        assert db.get_job(legacy)["owner_id"] == client.user_id

        self._second_user(client)
        orphan = db.create_job(topic="Another ownerless job")["id"]
        assert users.claim_ownerless_jobs() == 0         # two accounts: no guessing
        assert db.get_job(orphan)["owner_id"] is None


class TestWebSocketOwnership:
    def test_only_the_owner_from_an_allowed_origin_can_subscribe(self, client):
        import db
        import event_bus
        from starlette.websockets import WebSocketDisconnect

        job_id = db.create_job(topic="ws private", owner_id=client.user_id)["id"]
        other = client.post("/api/auth/signup", json={"email": "ws-intruder@example.test", "password": "test-password-3"},
                            headers={"Authorization": ""}).json()["token"]

        for headers in ({"Authorization": f"Bearer {other}"},            # not the owner
                        {"Origin": "http://evil.localhost:5000"}):     # foreign page
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/ws/{job_id}", headers=headers) as ws:
                    ws.receive_json()
            assert event_bus._subscribers.get(job_id, []) == []

        with client.websocket_connect(f"/ws/{job_id}", headers={"Origin": "http://localhost:3000"}) as ws:
            event_bus.emit(job_id, "router", "started", "owner sees this")
            assert ws.receive_json()["message"] == "owner sees this"
        event_bus.clear_job(job_id)
