"""
Request-level tests for the FastAPI route layer.

These drive the real application through TestClient against a throwaway SQLite
file. Exactly two things are stubbed and nothing else:

  * `evaluate_topic` — otherwise every job creation costs a live LLM call.
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

    import api.routes.jobs as jobs_routes

    dispatched: list[dict] = []
    monkeypatch.setattr(jobs_routes, "_run_pipeline", lambda **kw: dispatched.append(kw))

    from api.main import app

    with TestClient(app) as c:
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
