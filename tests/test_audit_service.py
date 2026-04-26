from sqlalchemy.orm import sessionmaker

from db.session import get_engine
from services import approval_service
from services.audit_service import AuditAction, list_for_resource, record
from services.job_service import create_job
from workers.tasks import CHAT_ORCHESTRATE_JOB_TYPE


def test_audit_records_on_approval_lifecycle_and_enqueue():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = create_job(session, job_type=CHAT_ORCHESTRATE_JOB_TYPE, payload={"x": 1})
        appr = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=None,
            job_id=job.id,
            payload={
                "gmail_draft_id": "draft:stub:x",
                "workflow": "email.outbound",
            },
        )
        aid = appr.id
        approval_service.approve(session, aid, actor="op", note="y")
        row = approval_service.get_request(session, aid)
        assert row is not None
        approval_service.enqueue_email_send_job(session, row)

    with factory() as session:
        events = list_for_resource(session, resource_type="approval", resource_id=aid)
        actions = [e.action for e in events]
        assert AuditAction.APPROVAL_CREATED in actions
        assert AuditAction.APPROVAL_APPROVED in actions
        assert AuditAction.SEND_JOB_ENQUEUED in actions


def test_send_succeeded_audit_on_job_resource():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        jid = record(
            session,
            action=AuditAction.SEND_JOB_SUCCEEDED,
            resource_type="job",
            resource_id="job-1",
            metadata={"approval_id": "a1"},
        ).id
    assert jid
