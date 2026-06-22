"""Trust Score endpoints (PR 18, v0). Read/compute; gated by `view_audit`; tenant-scoped.

Each call computes a fresh, fully explainable score from existing governance
evidence and persists it as a new version. Scores support governance review and
procurement validation; they are not a certification or guarantee of compliance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from services import trust_score_service
from services.rbac_service import Principal

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/score/{governed_action_id}")
def get_action_trust_score(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    """Explainable trust score for one governed action."""
    result = trust_score_service.score_action(
        db, governed_action_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="governed_action_not_found")
    return result


@router.get("/workflow/{workflow_id}")
def get_workflow_trust_score(
    workflow_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    """Explainable trust score aggregated over a workflow's governed actions."""
    result = trust_score_service.score_workflow(
        db, workflow_id=workflow_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return result


@router.get("/tenant/{tenant_id}")
def get_tenant_trust_score(
    tenant_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    """Explainable trust score aggregated over a tenant's governed actions.

    Tenant-scoped: a caller may only score its own resolved tenant.
    """
    if principal.tenant_id is not None and tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return trust_score_service.score_tenant(db, tenant_id=principal.tenant_id or tenant_id)
