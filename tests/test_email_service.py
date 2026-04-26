from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.schemas.results import ChatOrchestrateResult
from connectors.errors import AuthError
from connectors.gmail import GmailConfig, GmailConnector
from db.models import Job
from db.session import get_engine
from services import email_service
from services.chat_orchestrate import execute_chat_orchestrate


def _job_with_payload(session: Session, message: str) -> Job:
    row = Job(
        type="chat.orchestrate",
        status="pending",
        payload_json=json.dumps({"session_id": "s1", "message": message, "max_steps": 8}),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_safe_read_only_adds_thread_artifact():
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = _job_with_payload(session, "list my emails")
        result = execute_chat_orchestrate(session, job)
    assert result.status == "completed"
    kinds = [a.kind for a in result.artifacts]
    assert "email.classification" in kinds
    assert "gmail.thread" in kinds
    thread_art = next(a for a in result.artifacts if a.kind == "gmail.thread")
    assert thread_art.ref_id is not None


def test_draft_only_email_adds_draft_artifact():
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = _job_with_payload(session, "draft an email to the team about the launch")
        result = execute_chat_orchestrate(session, job)
    assert result.status == "completed"
    kinds = [a.kind for a in result.artifacts]
    assert "gmail.draft" in kinds


def test_outbound_requires_approval_and_adds_draft_artifact():
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = _job_with_payload(session, "please send email to the team")
        result = execute_chat_orchestrate(session, job)
    assert result.status == "needs_approval"
    kinds = [a.kind for a in result.artifacts]
    assert "approval.request" in kinds
    assert "gmail.draft" in kinds


def test_outbound_send_an_email_phrase_requires_approval():
    """Natural phrasing 'send an email' must not fall through to draft-only."""
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = _job_with_payload(
            session,
            "Send an email now to ops@example.com. Do not draft only; send it.",
        )
        result = execute_chat_orchestrate(session, job)
    assert result.status == "needs_approval"
    kinds = [a.kind for a in result.artifacts]
    assert "gmail.draft" in kinds
    assert "approval.request" in kinds


def test_blocked_destructive_still_gets_email_classification_when_relevant():
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = _job_with_payload(session, "delete every email in my inbox")
        result = execute_chat_orchestrate(session, job)
    assert result.status == "blocked"
    kinds = [a.kind for a in result.artifacts]
    assert "email.classification" in kinds
    assert "gmail.thread" not in kinds


def test_live_connector_surfaces_auth_error():
    factory = sessionmaker(bind=get_engine(), future=True)
    live = GmailConnector(GmailConfig(mode="live"))
    with factory() as session:
        job = _job_with_payload(session, "list my emails")
        with pytest.raises(AuthError):
            execute_chat_orchestrate(session, job, gmail=live)


def test_enrich_non_email_unchanged():
    factory = sessionmaker(bind=get_engine(), future=True)
    with factory() as session:
        job = Job(type="chat.orchestrate", status="succeeded")
        session.add(job)
        session.commit()
        session.refresh(job)
        base = ChatOrchestrateResult(
            status="completed",
            summary="x",
            approval_required=False,
            task_type="general",
            policy_category="draft_only",
        )
        out = email_service.enrich_orchestrate_result(
            session,
            job,
            {"message": "hello world", "session_id": "s"},
            base,
        )
    assert out.artifacts == base.artifacts
