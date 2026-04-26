"""Durable email thread and outbound delivery rows."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import EmailDeliveryRecord, EmailThreadRecord


def upsert_thread_record(
    session: Session,
    *,
    tenant_id: str | None,
    external_thread_id: str,
    source_job_id: str | None,
    snippet: str | None = None,
    intent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EmailThreadRecord:
    stmt = select(EmailThreadRecord).where(EmailThreadRecord.external_thread_id == external_thread_id)
    if tenant_id is None:
        stmt = stmt.where(EmailThreadRecord.tenant_id.is_(None))
    else:
        stmt = stmt.where(EmailThreadRecord.tenant_id == tenant_id)
    row = session.execute(stmt).scalar_one_or_none()
    extra_json = json.dumps(extra) if extra else None
    if row is None:
        row = EmailThreadRecord(
            tenant_id=tenant_id,
            external_thread_id=external_thread_id,
            last_snippet=snippet,
            last_intent=intent,
            source_job_id=source_job_id,
            extra_json=extra_json,
        )
        session.add(row)
    else:
        if snippet is not None:
            row.last_snippet = snippet
        if intent is not None:
            row.last_intent = intent
        if source_job_id is not None:
            row.source_job_id = source_job_id
        if extra_json is not None:
            row.extra_json = extra_json
        session.add(row)
    session.commit()
    session.refresh(row)
    return row


def upsert_outbound_delivery(
    session: Session,
    *,
    tenant_id: str | None,
    thread_external_id: str,
    gmail_draft_id: str,
    approval_id: str,
    source_job_id: str,
    status: str = "awaiting_approval",
) -> EmailDeliveryRecord:
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.approval_id == approval_id)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        row = EmailDeliveryRecord(
            tenant_id=tenant_id,
            thread_external_id=thread_external_id,
            gmail_draft_id=gmail_draft_id,
            approval_id=approval_id,
            source_job_id=source_job_id,
            status=status,
        )
        session.add(row)
    else:
        row.thread_external_id = thread_external_id
        row.gmail_draft_id = gmail_draft_id
        row.source_job_id = source_job_id
        row.status = status
        row.last_error = None
        session.add(row)
    session.commit()
    session.refresh(row)
    return row


def mark_delivery_sent(
    session: Session,
    *,
    approval_id: str,
    execution_job_id: str,
    gmail_message_id: str,
) -> None:
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.approval_id == approval_id)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        return
    row.gmail_message_id = gmail_message_id
    row.execution_job_id = execution_job_id
    row.status = "sent"
    row.last_error = None
    session.add(row)
    session.commit()


def mark_delivery_failed(session: Session, *, approval_id: str, execution_job_id: str, error: str) -> None:
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.approval_id == approval_id)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        return
    row.execution_job_id = execution_job_id
    row.status = "failed"
    row.last_error = error
    session.add(row)
    session.commit()


def list_deliveries(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[EmailDeliveryRecord]:
    stmt = select(EmailDeliveryRecord).order_by(EmailDeliveryRecord.updated_at.desc()).limit(min(limit, 200))
    if status:
        stmt = stmt.where(EmailDeliveryRecord.status == status)
    return list(session.execute(stmt).scalars().all())


def get_delivery_by_approval_id(session: Session, approval_id: str) -> EmailDeliveryRecord | None:
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.approval_id == approval_id).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def get_delivery_by_execution_job_id(session: Session, job_id: str) -> EmailDeliveryRecord | None:
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.execution_job_id == job_id).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def get_thread_summary(session: Session, *, tenant_id: str | None, external_thread_id: str) -> dict[str, Any]:
    stmt = select(EmailThreadRecord).where(EmailThreadRecord.external_thread_id == external_thread_id)
    if tenant_id is None:
        stmt = stmt.where(EmailThreadRecord.tenant_id.is_(None))
    else:
        stmt = stmt.where(EmailThreadRecord.tenant_id == tenant_id)
    thread = session.execute(stmt).scalar_one_or_none()
    d_stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.thread_external_id == external_thread_id)
    if tenant_id is None:
        d_stmt = d_stmt.where(EmailDeliveryRecord.tenant_id.is_(None))
    else:
        d_stmt = d_stmt.where(EmailDeliveryRecord.tenant_id == tenant_id)
    deliveries = list(session.execute(d_stmt).scalars().all())
    return {
        "thread": None
        if thread is None
        else {
            "id": thread.id,
            "external_thread_id": thread.external_thread_id,
            "last_snippet": thread.last_snippet,
            "last_intent": thread.last_intent,
            "source_job_id": thread.source_job_id,
        },
        "deliveries": [
            {
                "id": d.id,
                "approval_id": d.approval_id,
                "status": d.status,
                "gmail_draft_id": d.gmail_draft_id,
                "gmail_message_id": d.gmail_message_id,
                "source_job_id": d.source_job_id,
                "execution_job_id": d.execution_job_id,
                "last_error": d.last_error,
            }
            for d in deliveries
        ],
    }
