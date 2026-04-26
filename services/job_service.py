"""Create and update durable jobs; enqueue to workers outside request cycle."""

from __future__ import annotations

import json
from typing import Any

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ApprovalRequest, ApprovalStatus, EmailDeliveryRecord, Job, JobStatus
from services.job_types import EMAIL_SEND_APPROVED


def create_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    idempotency_key: str | None = None,
) -> Job:
    job = Job(
        type=job_type,
        tenant_id=tenant_id,
        status=JobStatus.pending.value,
        idempotency_key=idempotency_key,
        payload_json=json.dumps(payload) if payload is not None else None,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    # Worker dispatch hooks in workers/tasks.py (queue integration TBD).
    return job


def mark_job_failed(session: Session, job: Job, message: str) -> None:
    job.status = JobStatus.failed.value
    job.last_error = message
    session.add(job)
    session.commit()


def get_job_by_id(session: Session, job_id: str) -> Job | None:
    return session.get(Job, job_id)


def get_job_by_idempotency_key(session: Session, key: str) -> Job | None:
    stmt = select(Job).where(Job.idempotency_key == key).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def claim_next_pending(session: Session) -> Job | None:
    """Mark the oldest eligible pending job as running and return it, or None."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.pending.value)
        .where((Job.run_after.is_(None)) | (Job.run_after <= now))
        .order_by(Job.created_at)
        .limit(1)
    )
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.running.value
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(min(limit, 200))
    if status:
        stmt = stmt.where(Job.status == status)
    if job_type:
        stmt = stmt.where(Job.type == job_type)
    return list(session.execute(stmt).scalars().all())


def _assert_email_send_retry_allowed(session: Session, job: Job) -> None:
    """
    Retry rules for `email.send_approved`:
    - Allowed: job failed before a successful provider send (no gmail_message_id on approval).
    - Blocked: approval rejected (needs new approval flow).
    - Blocked: send already completed (gmail_message_id or delivery status sent).
    """
    payload = json.loads(job.payload_json or "{}")
    aid = payload.get("approval_id")
    if not aid:
        return
    appr = session.get(ApprovalRequest, aid)
    if appr is not None:
        if appr.status == ApprovalStatus.rejected.value:
            raise ValueError("retry_blocked_approval_rejected")
        body = json.loads(appr.payload_json or "{}")
        if body.get("gmail_message_id"):
            raise ValueError("retry_blocked_already_sent")
    stmt = select(EmailDeliveryRecord).where(EmailDeliveryRecord.approval_id == aid)
    row = session.execute(stmt).scalar_one_or_none()
    if row is not None and row.status == "sent" and row.gmail_message_id:
        raise ValueError("retry_blocked_delivery_sent")


def retry_failed_job(session: Session, job_id: str) -> Job:
    """Re-queue a failed `email.send_approved` job (idempotent send still enforced on approval row)."""
    job = get_job_by_id(session, job_id)
    if job is None:
        raise ValueError("job_not_found")
    if job.type != EMAIL_SEND_APPROVED:
        raise ValueError("job_not_retryable")
    if job.status != JobStatus.failed.value:
        raise ValueError("job_not_failed")
    _assert_email_send_retry_allowed(session, job)
    job.status = JobStatus.pending.value
    job.last_error = None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_job_succeeded(session: Session, job: Job, result: dict[str, Any] | None = None) -> None:
    if result is not None:
        base: dict[str, Any] = {}
        if job.payload_json:
            base = json.loads(job.payload_json)
        base["result"] = result
        job.payload_json = json.dumps(base)
    job.status = JobStatus.succeeded.value
    session.add(job)
    session.commit()
