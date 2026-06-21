"""Schemas for the policy version registry (PR 15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreatePolicyVersionRequest(BaseModel):
    version: str = Field(..., min_length=1)
    name: str = "ai_vendor_governance"
    change_reason: str | None = None
    rules: dict[str, Any] | None = None


class RollbackRequest(BaseModel):
    change_reason: str | None = None


class PolicyVersionResponse(BaseModel):
    id: str
    tenant_id: str | None = None
    name: str
    version: str
    status: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    change_reason: str | None = None
    created_at: datetime


class PolicyVersionListResponse(BaseModel):
    items: list[PolicyVersionResponse] = Field(default_factory=list)


def policy_to_response(row: Any) -> PolicyVersionResponse:
    return PolicyVersionResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        version=row.version,
        status=row.status,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        created_by_user_id=row.created_by_user_id,
        approved_by_user_id=row.approved_by_user_id,
        change_reason=row.change_reason,
        created_at=row.created_at,
    )
