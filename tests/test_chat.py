from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Job
from db.session import get_engine
from services.job_service import create_job
from workers.tasks import CHAT_ORCHESTRATE_JOB_TYPE, run_task


def test_chat_returns_queued_job():
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "tenant_id": None,
                "session_id": "sess-1",
                "message": "hello",
                "max_steps": 8,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["message"] == "Chat request accepted"
    assert len(data["job_id"]) == 36

    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = session.get(Job, data["job_id"])
        assert job is not None
        assert job.type == CHAT_ORCHESTRATE_JOB_TYPE
        assert job.status == "pending"


def test_chat_orchestrate_stub_marks_job_succeeded():
    with TestClient(app):
        pass

    engine = get_engine()
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        job = create_job(
            session,
            job_type=CHAT_ORCHESTRATE_JOB_TYPE,
            payload={"session_id": "s", "message": "m", "max_steps": 8},
        )
        job_id = job.id

    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        result = run_task(session, job)
        assert result == {"ok": True}

    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
