"""Operator approval actions: persist decision and enqueue execution jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_tenant_id, get_db, require_permission
from services.rbac_service import Principal
from app.schemas.approvals import (
    ApprovalDecisionResponse,
    ApprovalDetailResponse,
    ApproveRequestBody,
    RejectRequestBody,
    approval_to_detail,
)
from app.schemas.operator import ApprovalListResponse, approval_to_summary
from services import approval_service
from services.job_service import get_job_by_idempotency_key

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalListResponse)
def list_approvals_api(
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = approval_service.list_approvals(db, status=status, tenant_id=tenant_id, limit=limit)
    return ApprovalListResponse(items=[approval_to_summary(r) for r in rows])


def _enrich_approval_detail(db: Session, row) -> ApprovalDetailResponse:
    detail = approval_to_detail(row)
    ej = get_job_by_idempotency_key(db, f"email.send:{row.id}")
    return detail.model_copy(update={"execution_job_id": ej.id if ej else None})


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval(
    approval_id: str,
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
):
    row = approval_service.get_request(db, approval_id, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="approval_not_found")
    return _enrich_approval_detail(db, row)


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
def approve_request(
    approval_id: str,
    body: ApproveRequestBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("approve_action")),
):
    try:
        row = approval_service.approve(
            db, approval_id, actor=body.actor, note=body.note, tenant_id=principal.tenant_id
        )
    except ValueError as exc:
        # Cross-tenant / missing resource => 404 (consistent with read routes,
        # non-leaking); other validation failures => 400.
        status = 404 if str(exc) == "approval_not_found" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    execution_job_id: str | None = None
    if approval_service.should_enqueue_email_send_after_approval(row):
        try:
            send_job = approval_service.enqueue_email_send_job(db, row)
            execution_job_id = send_job.id
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    detail = _enrich_approval_detail(db, row)
    return ApprovalDecisionResponse(approval=detail, execution_job_id=execution_job_id)


@router.post("/{approval_id}/reject", response_model=ApprovalDetailResponse)
def reject_request(
    approval_id: str,
    body: RejectRequestBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("reject_action")),
):
    try:
        row = approval_service.reject(
            db, approval_id, actor=body.actor, reason=body.reason, tenant_id=principal.tenant_id
        )
    except ValueError as exc:
        status = 404 if str(exc) == "approval_not_found" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return _enrich_approval_detail(db, row)
