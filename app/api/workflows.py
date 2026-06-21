"""Governance review workflow endpoints (Phase 2).

Submit is gated by `create_governed_action` (Operator/Admin/Owner); reads by
`view_audit`. Approve/reject reuse `/approvals/*` (Reviewer/Compliance/Admin);
evidence export reuses `/evidence/packets/*`. All tenant-scoped via the principal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.schemas.workflows import (
    OverrideRequest,
    OverrideResponse,
    VendorGovernanceReviewRequest,
    WorkflowRunDetail,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowRunSummary,
    override_to_response,
)
from services import governance_workflow, override_service
from services.rbac_service import Principal

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/vendor-governance-review", response_model=WorkflowRunResponse)
def submit_vendor_governance_review(
    body: VendorGovernanceReviewRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("create_governed_action")),
):
    return governance_workflow.submit_vendor_governance_review(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.user_id or "operator",
        vendor_name=body.vendor_name,
        system_type=body.system_type,
        intended_use=body.intended_use,
        data_sensitivity=body.data_sensitivity,
        external_exposure=body.external_exposure,
        autonomy_level=body.autonomy_level,
    )


@router.get("/runs", response_model=WorkflowRunListResponse)
def list_runs(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    runs = governance_workflow.list_runs(db, tenant_id=principal.tenant_id)
    return WorkflowRunListResponse(items=[WorkflowRunSummary(**r) for r in runs])


@router.get("/runs/{governed_action_id}", response_model=WorkflowRunDetail)
def get_run(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    run = governance_workflow.get_run(
        db, governed_action_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return WorkflowRunDetail(**run)


@router.post("/runs/{governed_action_id}/override", response_model=OverrideResponse)
def override_run(
    governed_action_id: str,
    body: OverrideRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("override_high_risk_action")),
):
    """Record an authorized human override of a high-risk action (does NOT execute
    it). Requires the override authority permission."""
    try:
        row = override_service.create_override(
            db,
            tenant_id=principal.tenant_id,
            governed_action_id=governed_action_id,
            overridden_by=principal.user_id,
            reason=body.reason,
            authority_basis=body.authority_basis,
            compensating_control=body.compensating_control,
            accepted_risk=body.accepted_risk,
            expiration=body.expiration,
        )
    except ValueError as exc:
        status = 404 if str(exc) == "governed_action_not_found" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return override_to_response(row)
