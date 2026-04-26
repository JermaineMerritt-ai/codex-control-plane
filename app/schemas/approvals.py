"""Approval API models."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from db.models import ApprovalRequest


class ApproveRequestBody(BaseModel):
    actor: str = Field(..., min_length=1)
    note: str | None = None


class RejectRequestBody(BaseModel):
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ApprovalDetailResponse(BaseModel):
    id: str
    tenant_id: str | None
    kind: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] | None = None
    created_at: datetime
    decided_at: datetime | None = None
    source_job_id: str | None = Field(
        default=None,
        description="Linked chat/orchestrate job that created this approval.",
    )
    execution_job_id: str | None = Field(
        default=None,
        description="Enqueued `email.send_approved` job id when present.",
    )
    gmail_message_id: str | None = Field(default=None, description="Set after successful send.")
    send_status: str | None = Field(default=None, description="e.g. sent when outbound completed.")


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalDetailResponse
    execution_job_id: str | None = Field(
        default=None,
        description="Worker job id when a follow-up execution was enqueued (e.g. email.send_approved).",
    )


def approval_to_detail(row: ApprovalRequest) -> ApprovalDetailResponse:
    raw = json.loads(row.payload_json or "{}")
    data = dict(raw)
    decision = data.pop("decision", None)
    source_job_id = data.get("job_id")
    gmail_message_id = data.get("gmail_message_id")
    send_status = data.get("send_status")
    return ApprovalDetailResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=row.kind,
        status=row.status,
        payload=data,
        decision=decision,
        created_at=row.created_at,
        decided_at=row.decided_at,
        source_job_id=source_job_id,
        execution_job_id=None,
        gmail_message_id=gmail_message_id,
        send_status=send_status,
    )
