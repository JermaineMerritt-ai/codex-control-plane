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
    VendorGovernanceReviewRequest,
    WorkflowRunDetail,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowRunSummary,
)
from services import governance_workflow
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
