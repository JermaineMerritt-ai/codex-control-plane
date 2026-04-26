from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.session import get_engine
from services import approval_service
from services.job_service import create_job
from workers.tasks import CHAT_ORCHESTRATE_JOB_TYPE


def test_get_approval_not_found():
    with TestClient(app) as client:
        r = client.get("/approvals/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_approve_reject_and_get_roundtrip():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = create_job(session, job_type=CHAT_ORCHESTRATE_JOB_TYPE, payload={"x": 1})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=job.id,
            payload={"gmail_draft_id": "draft:stub:test"},
        )
        aid = appr.id

    with TestClient(app) as client:
        g = client.get(f"/approvals/{aid}")
        assert g.status_code == 200
        assert g.json()["status"] == "pending"
        assert g.json()["payload"]["gmail_draft_id"] == "draft:stub:test"

        dec = client.post(f"/approvals/{aid}/approve", json={"actor": "op1", "note": "go"})
        assert dec.status_code == 200
        body = dec.json()
        assert body["approval"]["status"] == "approved"
        assert body["execution_job_id"] is not None

        g2 = client.get(f"/approvals/{aid}")
        assert g2.json()["decision"]["status"] == "approved"


def test_reject_returns_detail():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = create_job(session, job_type=CHAT_ORCHESTRATE_JOB_TYPE, payload={"x": 1})
        appr = approval_service.create_request(session, kind="job.gate", tenant_id=None, job_id=job.id)
        aid = appr.id

    with TestClient(app) as client:
        r = client.post(f"/approvals/{aid}/reject", json={"actor": "op2", "reason": "nope"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
