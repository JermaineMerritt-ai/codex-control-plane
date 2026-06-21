"""Policy version registry endpoints (PR 15).

Reads gated by `view_audit`; lifecycle changes (create/activate/rollback) gated by
`manage_policies`. Tenant-scoped. Rollback = activate a previous version (forward
only); it never rewrites historical actions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.schemas.policies import (
    CreatePolicyVersionRequest,
    PolicyVersionListResponse,
    PolicyVersionResponse,
    RollbackRequest,
    policy_to_response,
)
from services import policy_version_service
from services.rbac_service import Principal

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=PolicyVersionListResponse)
def list_policies(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
    name: str | None = None,
):
    rows = policy_version_service.list_versions(db, tenant_id=principal.tenant_id, name=name)
    return PolicyVersionListResponse(items=[policy_to_response(r) for r in rows])


@router.post("", response_model=PolicyVersionResponse)
def create_policy(
    body: CreatePolicyVersionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("manage_policies")),
):
    row = policy_version_service.create_version(
        db, tenant_id=principal.tenant_id, name=body.name, version=body.version,
        rules=body.rules, created_by=principal.user_id, change_reason=body.change_reason,
    )
    return policy_to_response(row)


@router.get("/{version_id}", response_model=PolicyVersionResponse)
def get_policy(
    version_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    row = policy_version_service.get_version(db, version_id, tenant_id=principal.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="policy_version_not_found")
    return policy_to_response(row)


@router.post("/{version_id}/activate", response_model=PolicyVersionResponse)
def activate_policy(
    version_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("manage_policies")),
):
    try:
        row = policy_version_service.activate(
            db, version_id=version_id, approved_by=principal.user_id, tenant_id=principal.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return policy_to_response(row)


@router.post("/{version_id}/rollback", response_model=PolicyVersionResponse)
def rollback_policy(
    version_id: str,
    body: RollbackRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("manage_policies")),
):
    """Roll back by activating a previous version (supersedes current; forward-only)."""
    try:
        row = policy_version_service.rollback_to(
            db, version_id=version_id, approved_by=principal.user_id,
            change_reason=body.change_reason, tenant_id=principal.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return policy_to_response(row)
