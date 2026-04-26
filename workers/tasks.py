"""Task handlers: long-running work invoked by the queue, not HTTP."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from connectors.errors import ConnectorError
from db.models import Job
from services.audit_service import AuditAction, record as audit_record
from services.chat_orchestrate import execute_chat_orchestrate
from services.email_persistence import mark_delivery_failed
from services.email_service import run_send_approved_job
from services.job_service import mark_job_failed, mark_job_succeeded
from services.job_types import CHAT_ORCHESTRATE, EMAIL_SEND_APPROVED

logger = logging.getLogger(__name__)

CHAT_ORCHESTRATE_JOB_TYPE: str = CHAT_ORCHESTRATE
EMAIL_SEND_APPROVED_JOB_TYPE: str = EMAIL_SEND_APPROVED

TaskFn = Callable[[Session, Job], None]

_TASK_REGISTRY: dict[str, TaskFn] = {}


def register_task(job_type: str, fn: TaskFn) -> None:
    _TASK_REGISTRY[job_type] = fn


def run_task(session: Session, job: Job) -> dict[str, Any]:
    handler = _TASK_REGISTRY.get(job.type)
    if handler is None:
        return {"ok": False, "error": f"unknown_job_type:{job.type}"}
    handler(session, job)
    return {"ok": True}


def _handle_chat_orchestrate(session: Session, job: Job) -> None:
    """Validate payload, classify, apply policy, persist structured result."""
    logger.info("chat.orchestrate received job_id=%s", job.id)
    job.attempts = job.attempts + 1
    session.add(job)
    session.commit()
    session.refresh(job)
    try:
        result = execute_chat_orchestrate(session, job)
    except (json.JSONDecodeError, ValueError) as exc:
        mark_job_failed(session, job, str(exc))
        return
    except ConnectorError as exc:
        mark_job_failed(session, job, f"{type(exc).__name__}:{exc}")
        return
    mark_job_succeeded(session, job, result=result.model_dump(mode="json"))


def _handle_email_send_approved(session: Session, job: Job) -> None:
    """Execute operator-approved outbound send (stub or live connector)."""
    logger.info("email.send_approved job_id=%s", job.id)
    job.attempts = job.attempts + 1
    session.add(job)
    session.commit()
    session.refresh(job)
    try:
        result = run_send_approved_job(session, job)
    except ValueError as exc:
        mark_job_failed(session, job, str(exc))
        _audit_send_job_failed(session, job, str(exc))
        return
    except ConnectorError as exc:
        msg = f"{type(exc).__name__}:{exc}"
        mark_job_failed(session, job, msg)
        _audit_send_job_failed(session, job, msg)
        return
    mark_job_succeeded(session, job, result=result)


def _audit_send_job_failed(session: Session, job: Job, error: str) -> None:
    if job.type != EMAIL_SEND_APPROVED:
        return
    payload = json.loads(job.payload_json or "{}")
    aid = payload.get("approval_id")
    if aid:
        mark_delivery_failed(session, approval_id=aid, execution_job_id=job.id, error=error)
    audit_record(
        session,
        action=AuditAction.SEND_JOB_FAILED,
        resource_type="job",
        resource_id=job.id,
        tenant_id=job.tenant_id,
        metadata={"error": error, "approval_id": aid},
    )


register_task(CHAT_ORCHESTRATE_JOB_TYPE, _handle_chat_orchestrate)
register_task(EMAIL_SEND_APPROVED_JOB_TYPE, _handle_email_send_approved)
