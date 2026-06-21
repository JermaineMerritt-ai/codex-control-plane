"""Incident replay endpoint (PR 17). Read-only; gated by `view_audit`; tenant-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from services import incident_replay
from services.rbac_service import Principal

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/{governed_action_id}/replay")
def get_incident_replay(
    governed_action_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("view_audit")),
    format: str = Query(default="json", pattern="^(json|md)$"),
):
    """Reconstruct a governed action's timeline + evidence context (read-only)."""
    replay = incident_replay.build_incident_replay(
        db, governed_action_id=governed_action_id, tenant_id=principal.tenant_id
    )
    if replay is None:
        raise HTTPException(status_code=404, detail="governed_action_not_found")
    if format == "md":
        return PlainTextResponse(incident_replay.render_markdown(replay), media_type="text/markdown")
    return Response(content=incident_replay.render_json(replay), media_type="application/json")
