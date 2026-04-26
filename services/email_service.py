"""Governed email workflow: classify intent, stub read/draft, gate send via policy."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.email import EmailIntent
from app.schemas.results import ArtifactRef, ChatOrchestrateResult
from connectors.factory import get_gmail_connector
from connectors.gmail import GmailConfig, GmailConnector
from db.models import ApprovalRequest, Job
from services import approval_service
from services import email_persistence
from services.audit_service import AuditAction, record as audit_record
from services.job_types import EMAIL_SEND_APPROVED
from services.policy_service import OUTBOUND_PHRASE_MARKERS

_EMAIL_HINT = re.compile(r"thread[:=\s]+([A-Za-z0-9_-]+)", re.IGNORECASE)
_READ_MARKERS = ("list my emails", "fetch inbox", "read messages", "show thread")
_OUTBOUND_MARKERS = OUTBOUND_PHRASE_MARKERS


def is_email_related(message: str) -> bool:
    t = message.lower()
    if any(m in t for m in _OUTBOUND_MARKERS + _READ_MARKERS):
        return True
    if any(w in t for w in (" email", "email ", "gmail", "inbox", "reply to")):
        return True
    return False


def classify_email_intent(message: str) -> EmailIntent:
    """Label email workflow intent; only meaningful when `is_email_related` is true."""
    t = message.lower()
    if any(m in t for m in _OUTBOUND_MARKERS):
        return EmailIntent.outbound_send
    if any(m in t for m in _READ_MARKERS):
        return EmailIntent.inbox_read
    if ("draft" in t and "email" in t) or ("write" in t and "reply" in t) or ("compose" in t and "email" in t):
        return EmailIntent.draft_reply
    return EmailIntent.draft_reply


def parse_thread_hint(message: str, session_id: str) -> str:
    m = _EMAIL_HINT.search(message)
    if m:
        return m.group(1)
    return f"session:{session_id}"


def _default_connector(gmail: GmailConnector | None) -> GmailConnector:
    """Resolve connector from explicit override or central factory (env-driven)."""
    return gmail if gmail is not None else get_gmail_connector()


def workflow_read_thread(
    session: Session,
    conn: GmailConnector,
    *,
    thread_id: str,
    tenant_id: str | None,
    source_job_id: str,
    intent: EmailIntent,
) -> dict[str, Any]:
    """Read thread via connector and persist `EmailThreadRecord` for operators."""
    data = conn.read_thread(thread_id)
    email_persistence.upsert_thread_record(
        session,
        tenant_id=tenant_id,
        external_thread_id=str(data.get("thread_id")),
        snippet=str(data["snippet"]) if data.get("snippet") else None,
        source_job_id=source_job_id,
        intent=intent.value,
    )
    return data


def workflow_summarize_thread_state(
    session: Session,
    *,
    tenant_id: str | None,
    external_thread_id: str,
) -> dict[str, Any]:
    """Operator-facing snapshot of durable thread + delivery rows."""
    return email_persistence.get_thread_summary(
        session, tenant_id=tenant_id, external_thread_id=external_thread_id
    )


def enrich_orchestrate_result(
    session: Session,
    job: Job,
    payload: dict[str, Any],
    result: ChatOrchestrateResult,
    gmail: GmailConnector | None = None,
) -> ChatOrchestrateResult:
    """
    Attach email classification and stub Gmail artifacts when the message is email-related.

    Connector errors propagate so the worker can mark the job failed with a normalized reason.
    """
    message = str(payload.get("message", ""))
    if not is_email_related(message):
        return result

    conn = _default_connector(gmail)
    intent = classify_email_intent(message)
    thread_hint = parse_thread_hint(message, str(payload.get("session_id", "")))

    artifacts: list[ArtifactRef] = [
        ArtifactRef(
            kind="email.classification",
            metadata={
                "intent": intent.value,
                "thread_hint": thread_hint,
                "policy_category": result.policy_category,
            },
        ),
        *list(result.artifacts),
    ]
    summary = result.summary

    if result.status == "blocked":
        return result.model_copy(update={"artifacts": artifacts, "summary": summary})

    if result.status == "needs_approval" and intent is EmailIntent.outbound_send:
        draft_id = conn.create_draft(
            thread_id=thread_hint,
            subject="Outbound (pending approval)",
            body=message[:2000],
        )
        artifacts.append(
            ArtifactRef(
                kind="gmail.draft",
                ref_id=draft_id,
                metadata={"awaiting_approval": True, "thread_hint": thread_hint},
            )
        )
        summary = f"{summary} Draft prepared for gated send."
        if result.approval_id:
            approval_service.merge_execution_context(
                session,
                result.approval_id,
                {
                    "gmail_draft_id": draft_id,
                    "thread_hint": thread_hint,
                    "workflow": "email.outbound",
                },
            )
            email_persistence.upsert_outbound_delivery(
                session,
                tenant_id=job.tenant_id,
                thread_external_id=thread_hint,
                gmail_draft_id=draft_id,
                approval_id=result.approval_id,
                source_job_id=job.id,
                status="awaiting_approval",
            )
        return result.model_copy(update={"artifacts": artifacts, "summary": summary})

    if result.status == "completed":
        if intent is EmailIntent.inbox_read:
            data = workflow_read_thread(
                session,
                conn,
                thread_id=thread_hint,
                tenant_id=job.tenant_id,
                source_job_id=job.id,
                intent=intent,
            )
            artifacts.append(
                ArtifactRef(
                    kind="gmail.thread",
                    ref_id=str(data.get("thread_id")),
                    metadata={"snippet": data.get("snippet"), "message_count": data.get("message_count")},
                )
            )
            summary = f"{summary} Thread envelope loaded (stub)."
        elif intent is EmailIntent.draft_reply:
            email_persistence.upsert_thread_record(
                session,
                tenant_id=job.tenant_id,
                external_thread_id=thread_hint,
                source_job_id=job.id,
                intent=intent.value,
            )
            draft_id = conn.create_draft(
                thread_id=thread_hint,
                subject="Draft reply",
                body=f"Draft regarding: {message[:1500]}",
            )
            artifacts.append(
                ArtifactRef(
                    kind="gmail.draft",
                    ref_id=draft_id,
                    metadata={"thread_hint": thread_hint},
                )
            )
            summary = f"{summary} Draft created (stub)."

    return result.model_copy(update={"artifacts": artifacts, "summary": summary})


def validate_send_execution_invariants(session: Session, job: Job, approval: ApprovalRequest) -> None:
    """Harden send worker: job/approval linkage, tenant, job type."""
    if job.type != EMAIL_SEND_APPROVED:
        raise ValueError("invalid_execution_job_type")
    jp = json.loads(job.payload_json or "{}")
    if jp.get("approval_id") != approval.id:
        raise ValueError("execution_job_approval_mismatch")
    if job.tenant_id != approval.tenant_id:
        raise ValueError("tenant_mismatch_execution_job")
    approval_service.validate_send_enqueue_eligibility(session, approval)


def run_send_approved_job(session: Session, job: Job, gmail: GmailConnector | None = None) -> dict[str, Any]:
    """
    Worker entry: send Gmail draft after approval; persist structured result for inspection.

    Raises ValueError for invariant violations; ConnectorError for provider failures.
    """
    payload = json.loads(job.payload_json or "{}")
    approval_id = payload.get("approval_id")
    if not approval_id:
        raise ValueError("missing_approval_id")
    approval = approval_service.get_request(session, approval_id)
    if approval is None:
        raise ValueError("approval_not_found")

    validate_send_execution_invariants(session, job, approval)

    body = json.loads(approval.payload_json or "{}")
    draft_id = body.get("gmail_draft_id")
    if not draft_id:
        raise ValueError("missing_gmail_draft_id")

    existing_mid = body.get("gmail_message_id")
    if existing_mid:
        email_persistence.mark_delivery_sent(
            session,
            approval_id=approval_id,
            execution_job_id=job.id,
            gmail_message_id=str(existing_mid),
        )
        return _build_send_approved_result(
            approval_id=approval_id,
            source_job_id=body.get("job_id"),
            draft_id=draft_id,
            message_id=str(existing_mid),
            decision=body.get("decision") or {},
            deduped=True,
        )

    conn = _default_connector(gmail)
    message_id = conn.send_approved_draft(draft_id)
    approval_service.record_send_completed(session, approval_id, message_id)
    email_persistence.mark_delivery_sent(
        session,
        approval_id=approval_id,
        execution_job_id=job.id,
        gmail_message_id=message_id,
    )

    audit_record(
        session,
        action=AuditAction.SEND_JOB_SUCCEEDED,
        resource_type="job",
        resource_id=job.id,
        tenant_id=job.tenant_id,
        metadata={"approval_id": approval_id, "gmail_message_id": message_id},
    )

    return _build_send_approved_result(
        approval_id=approval_id,
        source_job_id=body.get("job_id"),
        draft_id=draft_id,
        message_id=message_id,
        decision=body.get("decision") or {},
        deduped=False,
    )


def _build_send_approved_result(
    *,
    approval_id: str,
    source_job_id: str | None,
    draft_id: str,
    message_id: str,
    decision: dict[str, Any],
    deduped: bool,
) -> dict[str, Any]:
    summary = (
        "Outbound message sent (stub)."
        if not deduped
        else "Send already completed (idempotent worker replay)."
    )
    return {
        "kind": "email.send_approved",
        "status": "sent",
        "summary": summary,
        "approval_id": approval_id,
        "source_job_id": source_job_id,
        "deduped": deduped,
        "artifacts": [
            {"kind": "gmail.message", "ref_id": message_id, "metadata": {"draft_id": draft_id}},
            {"kind": "approval.decision", "ref_id": approval_id, "metadata": {"decision": decision}},
        ],
    }
