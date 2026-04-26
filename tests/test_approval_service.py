import json

from sqlalchemy.orm import sessionmaker

from db.session import get_engine
from services import approval_service
from services.job_service import create_job
from workers.tasks import CHAT_ORCHESTRATE_JOB_TYPE


def test_create_approve_reject_roundtrip():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = create_job(session, job_type=CHAT_ORCHESTRATE_JOB_TYPE, payload={"x": 1})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=job.id,
            payload={"reason": "test"},
        )
        aid = appr.id
        assert appr.status == "pending"
        data = json.loads(appr.payload_json or "{}")
        assert data["job_id"] == job.id

    with factory() as session:
        approval_service.approve(session, aid, actor="operator-1", note="ok")

    with factory() as session:
        row = approval_service.get_request(session, aid)
        assert row is not None
        assert row.status == "approved"
        assert row.decided_at is not None
        body = json.loads(row.payload_json or "{}")
        assert body["decision"]["status"] == "approved"
        assert body["decision"]["actor"] == "operator-1"

    with factory() as session:
        job2 = create_job(session, job_type=CHAT_ORCHESTRATE_JOB_TYPE, payload={"y": 2})
        appr2 = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=job2.id,
        )
        aid2 = appr2.id

    with factory() as session:
        approval_service.reject(session, aid2, actor="operator-2", reason="no")

    with factory() as session:
        row2 = approval_service.get_request(session, aid2)
        assert row2 is not None
        assert row2.status == "rejected"
        body2 = json.loads(row2.payload_json or "{}")
        assert body2["decision"]["status"] == "rejected"
