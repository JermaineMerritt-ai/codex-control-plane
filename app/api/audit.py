"""Audit event listing for operators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.operator import (
    AuditChainVerificationResponse,
    AuditListResponse,
    audit_event_to_response,
)
from services.audit_service import list_audit_events, verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def list_audit(
    db: Session = Depends(get_db),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = list_audit_events(
        db, resource_type=resource_type, resource_id=resource_id, limit=limit
    )
    return AuditListResponse(items=[audit_event_to_response(r) for r in rows])


@router.get("/verify", response_model=AuditChainVerificationResponse)
def verify_audit_chain(db: Session = Depends(get_db)):
    """Recompute the tamper-evident audit hash chain and report its integrity."""
    result = verify_chain(db)
    return AuditChainVerificationResponse(
        status=result.status,
        ok=result.ok,
        verified_count=result.verified_count,
        total_count=result.total_count,
        broken_at_seq=result.broken_at_seq,
        reason=result.reason,
    )
