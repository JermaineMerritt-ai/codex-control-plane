from fastapi.testclient import TestClient

from app.main import app
from db.session import get_engine
from workers.runner import poll_once


def test_approve_enqueues_send_job_and_worker_sends():
    with TestClient(app) as client:
        create = client.post(
            "/chat",
            json={"session_id": "s-send", "message": "please send email to the team"},
        )
        chat_job_id = create.json()["job_id"]

    assert poll_once(get_engine()) is True

    with TestClient(app) as client:
        job_body = client.get(f"/jobs/{chat_job_id}").json()
    assert job_body["result"]["status"] == "needs_approval"
    approval_id = job_body["result"]["approval_id"]
    assert approval_id

    with TestClient(app) as client:
        appr = client.get(f"/approvals/{approval_id}").json()
    assert appr["payload"]["gmail_draft_id"].startswith("draft:stub:")

    with TestClient(app) as client:
        dec = client.post(
            f"/approvals/{approval_id}/approve",
            json={"actor": "operator", "note": "approved send"},
        )
        assert dec.status_code == 200
        exec_id = dec.json()["execution_job_id"]
        assert exec_id

    assert poll_once(get_engine()) is True

    with TestClient(app) as client:
        send_job = client.get(f"/jobs/{exec_id}").json()
    assert send_job["status"] == "succeeded"
    res = send_job["result"]
    assert res["kind"] == "email.send_approved"
    assert res["status"] == "sent"
    kinds = {a["kind"] for a in res["artifacts"]}
    assert "gmail.message" in kinds
    assert "approval.decision" in kinds
    msg_art = next(a for a in res["artifacts"] if a["kind"] == "gmail.message")
    assert msg_art["ref_id"].startswith("msg:stub:")


def test_approve_idempotent_execution_job():
    with TestClient(app) as client:
        create = client.post(
            "/chat",
            json={"session_id": "s-idem", "message": "send email to ops"},
        )
        chat_job_id = create.json()["job_id"]
    poll_once(get_engine())

    with TestClient(app) as client:
        approval_id = client.get(f"/jobs/{chat_job_id}").json()["result"]["approval_id"]
        r1 = client.post(f"/approvals/{approval_id}/approve", json={"actor": "a"})
        r2 = client.post(f"/approvals/{approval_id}/approve", json={"actor": "a"})
    assert r1.status_code == 200
    assert r2.status_code == 400
