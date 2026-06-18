"""List/summary models for operator visibility (not full dashboard UI)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from db.models import ApprovalRequest, AuditEvent, Job


class JobSummaryResponse(BaseModel):
    id: str
    type: str
    status: str
    tenant_id: str | None
    created_at: datetime


class JobListResponse(BaseModel):
    items: list[JobSummaryResponse] = Field(default_factory=list)


def job_to_summary(job: Job) -> JobSummaryResponse:
    return JobSummaryResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        tenant_id=job.tenant_id,
        created_at=job.created_at,
    )


class ApprovalSummaryResponse(BaseModel):
    id: str
    kind: str
    status: str
    tenant_id: str | None
    created_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalSummaryResponse] = Field(default_factory=list)


def approval_to_summary(row: ApprovalRequest) -> ApprovalSummaryResponse:
    return ApprovalSummaryResponse(
        id=row.id,
        kind=row.kind,
        status=row.status,
        tenant_id=row.tenant_id,
        created_at=row.created_at,
    )


class AuditEventResponse(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str
    tenant_id: str | None
    actor: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    seq: int | None = None
    previous_hash: str | None = None
    event_hash: str | None = None
    created_at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse] = Field(default_factory=list)


class AuditChainVerificationResponse(BaseModel):
    """Tamper-evidence verification status for the global audit chain."""

    status: str  # "verified" | "failed" | "empty"
    ok: bool
    verified_count: int
    total_count: int
    broken_at_seq: int | None = None
    reason: str | None = None


def audit_event_to_response(row: AuditEvent) -> AuditEventResponse:
    meta: dict[str, Any] = {}
    if row.metadata_json:
        meta = json.loads(row.metadata_json)
    return AuditEventResponse(
        id=row.id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        tenant_id=row.tenant_id,
        actor=row.actor,
        metadata=meta if isinstance(meta, dict) else {},
        seq=row.seq,
        previous_hash=row.previous_hash,
        event_hash=row.event_hash,
        created_at=row.created_at,
    )
