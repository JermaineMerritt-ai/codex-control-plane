from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.session import get_engine
from services.email_persistence import upsert_outbound_delivery, upsert_thread_record


def test_list_deliveries_and_get_by_approval():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        upsert_thread_record(
            session,
            tenant_id=None,
            external_thread_id="session:x",
            source_job_id="j1",
            intent="outbound_send",
        )
        upsert_outbound_delivery(
            session,
            tenant_id=None,
            thread_external_id="session:x",
            gmail_draft_id="draft:1",
            approval_id="ap-z",
            source_job_id="j1",
            status="awaiting_approval",
        )

    with TestClient(app) as client:
        lst = client.get("/email/deliveries", params={"status": "awaiting_approval"})
        assert lst.status_code == 200
        assert any(d["approval_id"] == "ap-z" for d in lst.json()["items"])

        one = client.get("/email/deliveries/by-approval/ap-z")
        assert one.status_code == 200
        assert one.json()["gmail_draft_id"] == "draft:1"

        miss = client.get("/email/deliveries/by-job/nonexistent")
        assert miss.status_code == 404


def test_thread_summary_endpoint():
    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        upsert_thread_record(
            session,
            tenant_id=None,
            external_thread_id="session:sum",
            source_job_id="j9",
            snippet="hello",
        )

    with TestClient(app) as client:
        r = client.get("/email/threads/session:sum/summary")
    assert r.status_code == 200
    assert r.json()["thread"]["last_snippet"] == "hello"
