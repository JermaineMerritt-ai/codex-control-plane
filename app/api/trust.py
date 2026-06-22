"""Trust Score endpoints (PR 18 v0; PR 19 read/compute split).

Reads are non-mutating: `GET /trust/...` returns the latest *stored* score (404 if
none has been computed yet) so procurement/audit review and version history never
change state. Computing a new score is an explicit write: `POST /trust/compute/...`
(gated by `export_evidence`). Scores are fully explainable (per-dimension
breakdown) and support governance review/procurement validation — not a
certification or guarantee of compliance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from services import trust_score_service
from services.rbac_service import Principal

router = APIRouter(prefix="/trust", tags=["trust"])


# --- Reads (non-mutating; latest stored score) -----------------------------

@router.get("/score/{governed_action_id}")
def get_action_trust_score(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    result = trust_score_service.latest_result(
        db, scope_type="governed_action", scope_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="trust_score_not_found")
    return result


@router.get("/workflow/{workflow_id}")
def get_workflow_trust_score(
    workflow_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    result = trust_score_service.latest_result(
        db, scope_type="workflow", scope_id=workflow_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="trust_score_not_found")
    return result


@router.get("/tenant/{tenant_id}")
def get_tenant_trust_score(
    tenant_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    if principal.tenant_id is not None and tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="trust_score_not_found")
    result = trust_score_service.latest_result(
        db, scope_type="tenant", scope_id=principal.tenant_id or tenant_id,
        tenant_id=principal.tenant_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="trust_score_not_found")
    return result


# --- Compute (explicit write; persists a new version) ----------------------

@router.post("/compute/{governed_action_id}")
def compute_action_trust_score(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("export_evidence")),
):
    result = trust_score_service.score_action(
        db, governed_action_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="governed_action_not_found")
    return result


@router.post("/compute/workflow/{workflow_id}")
def compute_workflow_trust_score(
    workflow_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("export_evidence")),
):
    result = trust_score_service.score_workflow(
        db, workflow_id=workflow_id, tenant_id=principal.tenant_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return result


@router.post("/compute/tenant/{tenant_id}")
def compute_tenant_trust_score(
    tenant_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("export_evidence")),
):
    if principal.tenant_id is not None and tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return trust_score_service.score_tenant(db, tenant_id=principal.tenant_id or tenant_id)
