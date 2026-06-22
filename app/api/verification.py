"""Procurement verification endpoints (PR 21).

Lifecycle: request -> review -> approve -> revoke (reject reachable from review on
bad evidence). Tenant-scoped; consumes signed evidence + trust score. Procurement
validation support only — not a certification or guarantee of compliance.

Permissions reuse existing RBAC (no new permission): requesting uses
`create_governed_action`; review/approve/revoke use `approve_action`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.schemas.verification import (
    ApproveVerificationBody,
    RequestVerificationBody,
    ReviewVerificationBody,
    RevokeVerificationBody,
    VerificationResponse,
    verification_to_response,
)
from services import verification_service
from services.rbac_service import Principal

router = APIRouter(prefix="/verification", tags=["verification"])

# ValueError code -> HTTP status.
_STATUS = {
    "subject_not_found": 404,
    "verification_not_found": 404,
    "no_signed_evidence": 422,
    "invalid_transition": 409,
    "insufficient_trust_score": 422,
}


def _raise(exc: ValueError) -> None:
    code = str(exc)
    status = 422 if code.startswith("evidence_not_valid") else _STATUS.get(code, 400)
    raise HTTPException(status_code=status, detail=code) from exc


@router.post("/request", response_model=VerificationResponse)
def request_verification(
    body: RequestVerificationBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("create_governed_action")),
):
    try:
        row = verification_service.request_verification(
            db, tenant_id=principal.tenant_id, subject_id=body.subject_id,
            subject_type=body.subject_type, min_score_required=body.min_score_required,
            requested_by=principal.user_id,
        )
    except ValueError as exc:
        _raise(exc)
    return verification_to_response(row)


@router.post("/review", response_model=VerificationResponse)
def review_verification(
    body: ReviewVerificationBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("approve_action")),
):
    try:
        row, ev = verification_service.review_verification(
            db, verification_id=body.verification_id, tenant_id=principal.tenant_id,
            reviewed_by=principal.user_id, notes=body.notes,
        )
    except ValueError as exc:
        _raise(exc)
    return verification_to_response(row, evidence=ev)


@router.post("/approve", response_model=VerificationResponse)
def approve_verification(
    body: ApproveVerificationBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("approve_action")),
):
    try:
        row, _score = verification_service.approve_verification(
            db, verification_id=body.verification_id, tenant_id=principal.tenant_id,
            approved_by=principal.user_id,
        )
    except ValueError as exc:
        _raise(exc)
    return verification_to_response(row)


@router.post("/revoke", response_model=VerificationResponse)
def revoke_verification(
    body: RevokeVerificationBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("approve_action")),
):
    try:
        row = verification_service.revoke_verification(
            db, verification_id=body.verification_id, tenant_id=principal.tenant_id,
            revoked_by=principal.user_id, reason=body.reason,
        )
    except ValueError as exc:
        _raise(exc)
    return verification_to_response(row)
