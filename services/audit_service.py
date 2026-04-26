"""Append-only audit trail for operator actions and job lifecycle."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AuditEvent


class AuditAction:
    APPROVAL_CREATED = "approval.created"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    SEND_JOB_ENQUEUED = "email.send_approved.enqueued"
    SEND_JOB_SUCCEEDED = "email.send_approved.succeeded"
    SEND_JOB_FAILED = "email.send_approved.failed"


def record(
    session: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant_id: str | None = None,
    actor: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    row = AuditEvent(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        actor=actor,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_audit_events(
    session: Session,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(limit, 500))
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    return list(session.execute(stmt).scalars().all())


def list_for_resource(session: Session, *, resource_type: str, resource_id: str) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.resource_type == resource_type, AuditEvent.resource_id == resource_id)
        .order_by(AuditEvent.created_at)
    )
    return list(session.execute(stmt).scalars().all())
