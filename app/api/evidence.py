"""Read-only evidence graph endpoints (PR 6).

Tenant-scoped and gated by `view_audit` (these return governance/evidence data).
Read assembly only — no export packet, no buyer-facing report (PR 7).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.schemas.evidence import (
    AiSystemListResponse,
    EvidenceGraphResponse,
    GovernedActionListResponse,
    ai_system_to_summary,
    governed_action_to_summary,
    graph_to_response,
)
from services import evidence_graph
from services.rbac_service import Principal

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/ai-systems", response_model=AiSystemListResponse)
def list_ai_systems(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    rows = evidence_graph.list_ai_systems(db, tenant_id=principal.tenant_id)
    return AiSystemListResponse(items=[ai_system_to_summary(r) for r in rows])


@router.get("/actions", response_model=GovernedActionListResponse)
def list_actions(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    rows = evidence_graph.list_governed_actions(db, tenant_id=principal.tenant_id)
    return GovernedActionListResponse(items=[governed_action_to_summary(r) for r in rows])


@router.get("/actions/{governed_action_id}/graph", response_model=EvidenceGraphResponse)
def get_action_graph(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
):
    graph = evidence_graph.get_evidence_graph(
        db, governed_action_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if graph is None:
        raise HTTPException(status_code=404, detail="governed_action_not_found")
    return graph_to_response(graph)
