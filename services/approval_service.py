"""Approval persistence: create, approve, reject, link to jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ApprovalRequest, ApprovalStatus, Job
from services.audit_service import AuditAction, record as audit_record
from services.job_service import create_job, get_job_by_idempotency_key
from services.job_types import EMAIL_SEND_APPROVED


def _validate_outbound_send_gate(session: Session, approval: ApprovalRequest) -> None:
    """Invariant checks for Gmail outbound gate approvals (draft present)."""
    if approval.kind != "job.gate":
        raise ValueError("approval_invalid_kind")
    data = json.loads(approval.payload_json or "{}")
    if not data.get("gmail_draft_id"):
        return
    wf = data.get("workflow")
    if wf is not None and wf != "email.outbound":
        raise ValueError("approval_wrong_workflow")
    sj = data.get("job_id")
    if not sj:
        raise ValueError("approval_missing_source_job")
    if session.get(Job, sj) is None:
        raise ValueError("source_job_not_found")


def validate_send_enqueue_eligibility(session: Session, approval: ApprovalRequest) -> None:
    """Eligibility for creating an `email.send_approved` worker job."""
    if approval.status != ApprovalStatus.approved.value:
        raise ValueError("approval_not_approved")
    _validate_outbound_send_gate(session, approval)
    data = json.loads(approval.payload_json or "{}")
    if not data.get("gmail_draft_id"):
        raise ValueError("missing_gmail_draft_id_for_enqueue")


def create_request(
    session: Session,
    *,
    kind: str,
    tenant_id: str | None,
    job_id: str,
    payload: dict[str, Any] | None = None,
) -> ApprovalRequest:
    body: dict[str, Any] = {"job_id": job_id}
    if payload:
        body.update(payload)
    row = ApprovalRequest(
        tenant_id=tenant_id,
        kind=kind,
        status=ApprovalStatus.pending.value,
        payload_json=json.dumps(body),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_record(
        session,
        action=AuditAction.APPROVAL_CREATED,
        resource_type="approval",
        resource_id=row.id,
        tenant_id=tenant_id,
        metadata={"kind": kind, "source_job_id": job_id},
    )
    return row


def approve(
    session: Session,
    approval_id: str,
    *,
    actor: str,
    note: str | None = None,
) -> ApprovalRequest:
    row = session.get(ApprovalRequest, approval_id)
    if row is None:
        raise ValueError("approval_not_found")
    if row.status != ApprovalStatus.pending.value:
        raise ValueError("approval_not_pending")
    data = json.loads(row.payload_json or "{}")
    if data.get("gmail_draft_id"):
        _validate_outbound_send_gate(session, row)
    data["decision"] = {"status": "approved", "actor": actor, "note": note}
    row.payload_json = json.dumps(data)
    row.status = ApprovalStatus.approved.value
    row.decided_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_record(
        session,
        action=AuditAction.APPROVAL_APPROVED,
        resource_type="approval",
        resource_id=row.id,
        tenant_id=row.tenant_id,
        actor=actor,
        metadata={"note": note},
    )
    return row


def reject(
    session: Session,
    approval_id: str,
    *,
    actor: str,
    reason: str,
) -> ApprovalRequest:
    row = session.get(ApprovalRequest, approval_id)
    if row is None:
        raise ValueError("approval_not_found")
    if row.status != ApprovalStatus.pending.value:
        raise ValueError("approval_not_pending")
    data = json.loads(row.payload_json or "{}")
    data["decision"] = {"status": "rejected", "actor": actor, "reason": reason}
    row.payload_json = json.dumps(data)
    row.status = ApprovalStatus.rejected.value
    row.decided_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_record(
        session,
        action=AuditAction.APPROVAL_REJECTED,
        resource_type="approval",
        resource_id=row.id,
        tenant_id=row.tenant_id,
        actor=actor,
        metadata={"reason": reason},
    )
    return row


def get_request(session: Session, approval_id: str) -> ApprovalRequest | None:
    return session.get(ApprovalRequest, approval_id)


def list_approvals(session: Session, *, status: str | None = None, limit: int = 50) -> list[ApprovalRequest]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(min(limit, 200))
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    return list(session.execute(stmt).scalars().all())


def merge_execution_context(session: Session, approval_id: str, fields: dict[str, Any]) -> ApprovalRequest:
    """Merge fields into approval payload (e.g. gmail_draft_id after draft creation)."""
    row = session.get(ApprovalRequest, approval_id)
    if row is None:
        raise ValueError("approval_not_found")
    data = json.loads(row.payload_json or "{}")
    data.update(fields)
    row.payload_json = json.dumps(data)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def record_send_completed(session: Session, approval_id: str, gmail_message_id: str) -> ApprovalRequest:
    """Persist outbound send outcome on the approval (idempotency anchor for workers)."""
    return merge_execution_context(
        session,
        approval_id,
        {"gmail_message_id": gmail_message_id, "send_status": "sent"},
    )


def should_enqueue_email_send_after_approval(approval: ApprovalRequest) -> bool:
    """True when an approved Gmail draft exists and should be sent via worker."""
    if approval.kind != "job.gate":
        return False
    data = json.loads(approval.payload_json or "{}")
    if not data.get("gmail_draft_id"):
        return False
    wf = data.get("workflow")
    if wf is not None and wf != "email.outbound":
        return False
    return True


def enqueue_email_send_job(session: Session, approval: ApprovalRequest) -> Job:
    """Idempotently create `email.send_approved` job for worker execution."""
    validate_send_enqueue_eligibility(session, approval)
    key = f"email.send:{approval.id}"
    existing = get_job_by_idempotency_key(session, key)
    if existing is not None:
        audit_record(
            session,
            action=AuditAction.SEND_JOB_ENQUEUED,
            resource_type="approval",
            resource_id=approval.id,
            tenant_id=approval.tenant_id,
            metadata={"job_id": existing.id, "idempotent": True},
        )
        return existing
    send_job = create_job(
        session,
        job_type=EMAIL_SEND_APPROVED,
        tenant_id=approval.tenant_id,
        payload={"approval_id": approval.id},
        idempotency_key=key,
    )
    audit_record(
        session,
        action=AuditAction.SEND_JOB_ENQUEUED,
        resource_type="approval",
        resource_id=approval.id,
        tenant_id=approval.tenant_id,
        metadata={"job_id": send_job.id},
    )
    return send_job
