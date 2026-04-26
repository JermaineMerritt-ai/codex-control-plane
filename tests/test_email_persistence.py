from sqlalchemy.orm import sessionmaker

from db.session import get_engine
from services.email_persistence import upsert_outbound_delivery, upsert_thread_record
from services.email_service import workflow_summarize_thread_state


def test_thread_and_delivery_roundtrip():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        upsert_thread_record(
            session,
            tenant_id=None,
            external_thread_id="session:abc",
            source_job_id="job-1",
            snippet="hi",
            intent="inbox_read",
        )
        upsert_outbound_delivery(
            session,
            tenant_id=None,
            thread_external_id="session:abc",
            gmail_draft_id="draft:stub:1",
            approval_id="ap-1",
            source_job_id="job-2",
            status="awaiting_approval",
        )

    with factory() as session:
        snap = workflow_summarize_thread_state(
            session, tenant_id=None, external_thread_id="session:abc"
        )
    assert snap["thread"] is not None
    assert snap["thread"]["last_intent"] == "inbox_read"
    assert len(snap["deliveries"]) == 1
    assert snap["deliveries"][0]["gmail_draft_id"] == "draft:stub:1"
