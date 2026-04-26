from fastapi.testclient import TestClient

from app.main import app
from db.session import get_engine
from services.job_service import create_job
from services.job_types import EMAIL_SEND_APPROVED
from sqlalchemy.orm import sessionmaker


def test_list_jobs_filter():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        create_job(session, job_type="chat.orchestrate", payload={})
        failed = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            payload={"approval_id": "x"},
        )
        failed.status = "failed"
        session.add(failed)
        session.commit()
        failed_id = failed.id

    with TestClient(app) as client:
        r = client.get("/jobs", params={"status": "failed"})
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()["items"]}
        assert failed_id in ids


def test_list_approvals():
    with TestClient(app) as client:
        r = client.get("/approvals", params={"status": "pending", "limit": 5})
    assert r.status_code == 200
    assert "items" in r.json()


def test_list_audit():
    with TestClient(app) as client:
        r = client.get("/audit", params={"resource_type": "approval", "limit": 10})
    assert r.status_code == 200
    assert "items" in r.json()


def test_retry_failed_send_job():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        j = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            payload={"approval_id": "a1"},
        )
        j.status = "failed"
        j.last_error = "boom"
        session.add(j)
        session.commit()
        jid = j.id

    with TestClient(app) as client:
        r = client.post(f"/jobs/{jid}/retry")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_retry_rejects_non_failed():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        j = create_job(session, job_type=EMAIL_SEND_APPROVED, payload={})
        jid = j.id
    with TestClient(app) as client:
        r = client.post(f"/jobs/{jid}/retry")
    assert r.status_code == 400


def test_retry_blocked_when_send_already_recorded():
    from services import approval_service

    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={
                "gmail_draft_id": "draft:x",
                "workflow": "email.outbound",
                "gmail_message_id": "msg:sent",
                "send_status": "sent",
            },
        )
        approval_service.approve(session, appr.id, actor="op")
        j = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            payload={"approval_id": appr.id},
        )
        j.status = "failed"
        session.add(j)
        session.commit()
        jid = j.id

    with TestClient(app) as client:
        r = client.post(f"/jobs/{jid}/retry")
    assert r.status_code == 400
    assert "retry_blocked" in r.json()["detail"]
