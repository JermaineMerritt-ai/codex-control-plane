"""Audit event listing for operators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_tenant_id, get_db
from app.schemas.operator import (
    AuditChainVerificationResponse,
    AuditListResponse,
    audit_event_to_response,
)
from services.audit_service import list_audit_events, verify_chain, verify_tenant_events

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def list_audit(
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = list_audit_events(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        limit=limit,
    )
    return AuditListResponse(items=[audit_event_to_response(r) for r in rows])


@router.get("/verify", response_model=AuditChainVerificationResponse)
def verify_audit_chain(
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
):
    """Verify audit integrity.

    A tenant-bound caller verifies only its own events (self-hash integrity of
    that tenant's records); it cannot see or verify another tenant's view, nor
    learn the global event count. The operator/system path (no API key) runs the
    full global hash-chain verification.
    """
    if tenant_id is not None:
        result = verify_tenant_events(db, tenant_id)
    else:
        result = verify_chain(db)
    return AuditChainVerificationResponse(
        status=result.status,
        ok=result.ok,
        verified_count=result.verified_count,
        total_count=result.total_count,
        broken_at_seq=result.broken_at_seq,
        reason=result.reason,
    )
