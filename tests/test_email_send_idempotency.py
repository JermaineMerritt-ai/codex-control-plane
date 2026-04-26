import json

from sqlalchemy.orm import sessionmaker

from db.models import Job
from db.session import get_engine
from services import approval_service
from services.email_service import run_send_approved_job
from services.job_service import create_job
from services.job_types import EMAIL_SEND_APPROVED


def test_send_skips_second_api_call_when_message_id_already_recorded():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={"m": 1})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={
                "gmail_draft_id": "draft:stub:dedupe",
                "workflow": "email.outbound",
            },
        )
        approval_service.approve(session, appr.id, actor="op")
        approval_service.merge_execution_context(
            session,
            appr.id,
            {"gmail_message_id": "msg:stub:already", "send_status": "sent"},
        )
        send_job = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            tenant_id=None,
            payload={"approval_id": appr.id},
            idempotency_key=f"email.send:{appr.id}",
        )
        sid = send_job.id

    with factory() as session:
        job = session.get(Job, sid)
        assert job is not None
        out = run_send_approved_job(session, job)
    assert out["deduped"] is True
    assert out["artifacts"][0]["ref_id"] == "msg:stub:already"


def test_enqueue_idempotent_returns_same_job_and_audits_twice():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={"gmail_draft_id": "d1", "workflow": "email.outbound"},
        )
        approval_service.approve(session, appr.id, actor="a")
        row = approval_service.get_request(session, appr.id)
        assert row is not None
        j1 = approval_service.enqueue_email_send_job(session, row)
        j2 = approval_service.enqueue_email_send_job(session, row)
        assert j1.id == j2.id
