import pytest
from sqlalchemy.orm import sessionmaker

from connectors.errors import AuthError, TemporaryProviderError
from connectors.gmail import GmailConfig, GmailConnector
from db.models import Job
from db.session import get_engine
from services import approval_service
from services.email_service import run_send_approved_job
from services.job_service import create_job
from services.job_types import EMAIL_SEND_APPROVED
from workers.tasks import _handle_email_send_approved


def test_cannot_approve_outbound_gate_with_wrong_workflow():
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
                "workflow": "invoice.pay",
            },
        )
        with pytest.raises(ValueError, match="approval_wrong_workflow"):
            approval_service.approve(session, appr.id, actor="op")


def test_send_fails_when_approval_not_approved():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={"gmail_draft_id": "d", "workflow": "email.outbound"},
        )
        send_job = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            tenant_id=None,
            payload={"approval_id": appr.id},
        )
        jid = send_job.id
    with factory() as session:
        job = session.get(Job, jid)
        assert job is not None
        with pytest.raises(ValueError, match="approval_not_approved"):
            run_send_approved_job(session, job)


def test_send_fails_tenant_mismatch():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={}, tenant_id="t1")
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id="t1",
            job_id=chat.id,
            payload={"gmail_draft_id": "d", "workflow": "email.outbound"},
        )
        approval_service.approve(session, appr.id, actor="op")
        send_job = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            tenant_id="t2",
            payload={"approval_id": appr.id},
        )
        jid = send_job.id
    with factory() as session:
        job = session.get(Job, jid)
        assert job is not None
        with pytest.raises(ValueError, match="tenant_mismatch"):
            run_send_approved_job(session, job)


def test_connector_failure_marks_job_failed_and_audits(monkeypatch):
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={"gmail_draft_id": "d", "workflow": "email.outbound"},
        )
        approval_service.approve(session, appr.id, actor="op")
        send_job = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            tenant_id=None,
            payload={"approval_id": appr.id},
        )
        jid = send_job.id

    def _boom(self, draft_id: str) -> str:
        raise TemporaryProviderError("provider down", provider="gmail")

    monkeypatch.setattr(GmailConnector, "send_approved_draft", _boom)

    with factory() as session:
        job = session.get(Job, jid)
        assert job is not None
        _handle_email_send_approved(session, job)
        session.refresh(job)
    assert job.status == "failed"


def test_live_mode_auth_failure_on_send():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={"gmail_draft_id": "d", "workflow": "email.outbound"},
        )
        approval_service.approve(session, appr.id, actor="op")
        send_job = create_job(
            session,
            job_type=EMAIL_SEND_APPROVED,
            tenant_id=None,
            payload={"approval_id": appr.id},
        )
        jid = send_job.id
    with factory() as session:
        job = session.get(Job, jid)
        assert job is not None
        with pytest.raises(AuthError):
            run_send_approved_job(session, job, gmail=GmailConnector(GmailConfig(mode="live")))


def test_invalid_job_type_for_send_handler():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        chat = create_job(session, job_type="chat.orchestrate", payload={})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=chat.id,
            payload={"gmail_draft_id": "d", "workflow": "email.outbound"},
        )
        approval_service.approve(session, appr.id, actor="op")
        bad = create_job(
            session,
            job_type="chat.orchestrate",
            tenant_id=None,
            payload={"approval_id": appr.id},
        )
        bid = bad.id
    with factory() as session:
        job = session.get(Job, bid)
        assert job is not None
        with pytest.raises(ValueError, match="invalid_execution_job_type"):
            run_send_approved_job(session, job)
