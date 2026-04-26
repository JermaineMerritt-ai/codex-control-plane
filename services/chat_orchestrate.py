"""chat.orchestrate: validate payload, classify, apply policy, optional approval record."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.results import ArtifactRef, ChatOrchestrateResult
from connectors.gmail import GmailConnector
from db.models import Job
from services import approval_service, email_service
from services.policy_service import PolicyCategory, classify_message_policy_category, evaluate_action

_REQUIRED_PAYLOAD_KEYS = ("session_id", "message", "max_steps")


def _validate_payload(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in _REQUIRED_PAYLOAD_KEYS if k not in raw]
    if missing:
        raise ValueError(f"missing_fields:{','.join(missing)}")
    session_id = raw["session_id"]
    message = raw["message"]
    max_steps = raw["max_steps"]
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("invalid_session_id")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("invalid_message")
    if not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("invalid_max_steps")
    return {"session_id": session_id.strip(), "message": message.strip(), "max_steps": max_steps}


def _task_type_label(category: PolicyCategory, message: str) -> str:
    if category is PolicyCategory.read_only:
        return "inbox_read"
    if category is PolicyCategory.outbound_send:
        return "outbound_message"
    if category is PolicyCategory.publish:
        return "publish_request"
    if category is PolicyCategory.destructive:
        return "destructive_request"
    if re.search(r"\b(script|draft|caption|thumbnail|post)\b", message.lower()):
        return "content_draft"
    return "general"


def execute_chat_orchestrate(
    session: Session,
    job: Job,
    gmail: GmailConnector | None = None,
) -> ChatOrchestrateResult:
    data = json.loads(job.payload_json or "{}")
    payload = _validate_payload(data)

    category = classify_message_policy_category(payload["message"])
    evaluation = evaluate_action(category)
    task_type = _task_type_label(category, payload["message"])

    if evaluation.blocked or not evaluation.allowed:
        result = ChatOrchestrateResult(
            status="blocked",
            summary=evaluation.reason or "blocked_by_policy",
            approval_required=False,
            next_action=None,
            task_type=task_type,
            policy_category=category.value,
        )
        return email_service.enrich_orchestrate_result(session, job, payload, result, gmail=gmail)

    if evaluation.requires_approval:
        approval = approval_service.create_request(
            session,
            kind="job.gate",
            tenant_id=job.tenant_id,
            job_id=job.id,
            payload={"policy_category": category.value, "task_type": task_type},
        )
        result = ChatOrchestrateResult(
            status="needs_approval",
            summary=evaluation.reason or "approval_required",
            artifacts=[
                ArtifactRef(
                    kind="approval.request",
                    ref_id=approval.id,
                    metadata={"kind": approval.kind},
                )
            ],
            approval_required=True,
            next_action="await_approval",
            task_type=task_type,
            policy_category=category.value,
            approval_id=approval.id,
        )
        return email_service.enrich_orchestrate_result(session, job, payload, result, gmail=gmail)

    result = ChatOrchestrateResult(
        status="completed",
        summary="Classified and cleared policy; orchestration stub (no LLM or connectors).",
        approval_required=False,
        next_action=None,
        task_type=task_type,
        policy_category=category.value,
    )
    return email_service.enrich_orchestrate_result(session, job, payload, result, gmail=gmail)
