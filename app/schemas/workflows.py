"""Schemas for the governance review workflow (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OverrideRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    authority_basis: str = Field(..., min_length=1)
    compensating_control: str = Field(..., min_length=1)
    accepted_risk: str | None = None
    expiration: datetime | None = None  # metadata-only in the pilot (not enforced)


class OverrideResponse(BaseModel):
    id: str
    governed_action_id: str
    overridden_by_user_id: str | None = None
    reason: str
    authority_basis: str
    accepted_risk: str | None = None
    compensating_control: str
    expiration: datetime | None = None
    status: str
    created_at: datetime


def override_to_response(row: Any) -> "OverrideResponse":
    return OverrideResponse(
        id=row.id,
        governed_action_id=row.governed_action_id,
        overridden_by_user_id=row.overridden_by_user_id,
        reason=row.reason,
        authority_basis=row.authority_basis,
        accepted_risk=row.accepted_risk,
        compensating_control=row.compensating_control,
        expiration=row.expiration,
        status=row.status,
        created_at=row.created_at,
    )


class VendorGovernanceReviewRequest(BaseModel):
    vendor_name: str = Field(..., min_length=1)
    system_type: str = Field(..., min_length=1)
    intended_use: str = Field(..., min_length=1)
    data_sensitivity: str | None = None  # e.g. none/internal/pii/phi/regulated
    external_exposure: bool = False
    autonomy_level: str | None = None  # e.g. none/assisted/semi_autonomous/autonomous


class PolicyView(BaseModel):
    category: str
    requires_approval: bool
    blocked: bool
    reason: str | None = None


class RiskView(BaseModel):
    level: str
    score: int
    reasons: list[str] = Field(default_factory=list)


class WorkflowRunResponse(BaseModel):
    governed_action_id: str
    action_type: str
    status: str
    requires_approval: bool
    approval_id: str | None = None
    policy: PolicyView
    risk: RiskView


class WorkflowRunDetail(BaseModel):
    governed_action_id: str
    action_type: str
    status: str
    approval_id: str | None = None
    approval_status: str | None = None
    policy: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    intake: dict[str, Any] | None = None
    audit_event_count: int = 0
    evidence_artifact_count: int = 0


class WorkflowRunSummary(BaseModel):
    governed_action_id: str
    status: str
    approval_id: str | None = None
    risk: dict[str, Any] | None = None
    policy_decision: str | None = None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunSummary] = Field(default_factory=list)
