from fastapi.testclient import TestClient

from app.main import app
from db.session import get_engine
from workers.runner import poll_once


def test_get_job_not_found():
    with TestClient(app) as client:
        response = client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "job_not_found"


def test_get_job_after_chat_is_pending_then_runner_succeeds():
    with TestClient(app) as client:
        create = client.post(
            "/chat",
            json={"session_id": "s1", "message": "hi"},
        )
        assert create.status_code == 200
        job_id = create.json()["job_id"]

        pending = client.get(f"/jobs/{job_id}")
        assert pending.status_code == 200
        body = pending.json()
        assert body["id"] == job_id
        assert body["status"] == "pending"
        assert body["type"] == "chat.orchestrate"
        assert body["attempts"] == 0
        assert body["payload"]["session_id"] == "s1"
        assert body["payload"]["message"] == "hi"
        assert body["result"] is None

    assert poll_once(get_engine()) is True

    with TestClient(app) as client:
        done = client.get(f"/jobs/{job_id}")
    assert done.status_code == 200
    final = done.json()
    assert final["status"] == "succeeded"
    assert final["attempts"] == 1
    assert final["result"] is not None
    assert final["result"]["kind"] == "chat.orchestrate"
    assert final["result"]["status"] == "completed"
    assert final["result"]["approval_required"] is False
    assert final["payload"]["session_id"] == "s1"
    assert "result" not in final["payload"]


def test_job_needs_approval_when_message_requests_send():
    with TestClient(app) as client:
        create = client.post(
            "/chat",
            json={"session_id": "s2", "message": "please send email to the team"},
        )
        job_id = create.json()["job_id"]
    assert poll_once(get_engine()) is True
    with TestClient(app) as client:
        body = client.get(f"/jobs/{job_id}").json()
    assert body["result"]["status"] == "needs_approval"
    assert body["result"]["approval_required"] is True
    assert body["result"]["approval_id"] is not None
    assert body["result"]["next_action"] == "await_approval"


def test_job_blocked_for_destructive_message():
    with TestClient(app) as client:
        create = client.post(
            "/chat",
            json={"session_id": "s3", "message": "delete all old records now"},
        )
        job_id = create.json()["job_id"]
    assert poll_once(get_engine()) is True
    with TestClient(app) as client:
        body = client.get(f"/jobs/{job_id}").json()
    assert body["result"]["status"] == "blocked"
    assert body["result"]["approval_required"] is False
