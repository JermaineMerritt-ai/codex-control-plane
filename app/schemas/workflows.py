"""Schemas for the governance review workflow (Phase 2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
