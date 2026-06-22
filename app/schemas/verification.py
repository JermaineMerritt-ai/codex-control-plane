"""Schemas for the procurement verification lifecycle (PR 21)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RequestVerificationBody(BaseModel):
    subject_id: str
    subject_type: str = "governed_action"
    min_score_required: int = 60


class ReviewVerificationBody(BaseModel):
    verification_id: str
    notes: str | None = None


class ApproveVerificationBody(BaseModel):
    verification_id: str


class RevokeVerificationBody(BaseModel):
    verification_id: str
    reason: str


class VerificationResponse(BaseModel):
    id: str
    tenant_id: str | None = None
    subject_type: str
    subject_id: str
    status: str
    evidence_packet_id: str | None = None
    trust_score: int | None = None
    trust_score_id: str | None = None
    min_score_required: int
    decision_reason: str | None = None
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime
    # Optional context attached on review/approve responses.
    evidence_status: str | None = None
    evidence_reasons: list[str] = Field(default_factory=list)


def verification_to_response(
    row: Any, *, evidence: dict[str, Any] | None = None
) -> VerificationResponse:
    return VerificationResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        status=row.status,
        evidence_packet_id=row.evidence_packet_id,
        trust_score=row.trust_score,
        trust_score_id=row.trust_score_id,
        min_score_required=row.min_score_required,
        decision_reason=row.decision_reason,
        review_notes=row.review_notes,
        reviewed_at=row.reviewed_at,
        decided_at=row.decided_at,
        created_at=row.created_at,
        evidence_status=(evidence or {}).get("status"),
        evidence_reasons=(evidence or {}).get("reasons", []),
    )
