"""Human override registry (PR 16 — pilot scope).

Records an authorized human override of a HIGH-risk (or medium-risk) governed
action. An override is a recorded authorization decision (status
`override_recorded`) — it does NOT execute the action. `expiration` is captured
as metadata only (not enforced in the pilot). Authority is enforced at the API
layer via the `override_high_risk_action` permission.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ActionOverride
from services import audit_service, evidence_graph

OVERRIDABLE_RISK = ("medium", "high")
STATUS_RECORDED = "override_recorded"


def _action_risk_level(action: Any) -> str | None:
    if not action.metadata_json:
        return None
    meta = json.loads(action.metadata_json)
    return (meta.get("risk") or {}).get("level")


def create_override(
    session: Session,
    *,
    tenant_id: str | None,
    governed_action_id: str,
    overridden_by: str | None,
    reason: str,
    authority_basis: str,
    compensating_control: str,
    accepted_risk: str | None = None,
    expiration: datetime | None = None,
) -> ActionOverride:
    """Record an override for a high/medium-risk governed action.

    Raises ValueError('governed_action_not_found') if missing/cross-tenant, or
    ('override_not_applicable') if the action is not medium/high risk.
    """
    action = evidence_graph.get_governed_action(session, governed_action_id, tenant_id=tenant_id)
    if action is None:
        raise ValueError("governed_action_not_found")

    risk_level = accepted_risk or _action_risk_level(action)
    if (_action_risk_level(action) or "") not in OVERRIDABLE_RISK:
        raise ValueError("override_not_applicable")

    row = ActionOverride(
        tenant_id=tenant_id,
        governed_action_id=governed_action_id,
        overridden_by_user_id=overridden_by,
        reason=reason,
        authority_basis=authority_basis,
        accepted_risk=risk_level,
        compensating_control=compensating_control,
        expiration=expiration,
        status=STATUS_RECORDED,
    )
    session.add(row)

    # Reflect the recorded override on the action WITHOUT executing it.
    action.status = STATUS_RECORDED
    session.add(action)
    session.commit()
    session.refresh(row)

    audit_service.record(
        session,
        action="governed_action.overridden",
        resource_type="governed_action",
        resource_id=governed_action_id,
        tenant_id=tenant_id,
        actor=overridden_by,
        metadata={
            "override_id": row.id,
            "accepted_risk": risk_level,
            "authority_basis": authority_basis,
            "compensating_control": compensating_control,
            "expiration": expiration.isoformat() if expiration else None,
            "note": "recorded authorization; does not execute the action",
        },
    )
    return row


def list_overrides_for_action(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None
) -> list[ActionOverride]:
    stmt = select(ActionOverride).where(
        ActionOverride.governed_action_id == governed_action_id
    ).order_by(ActionOverride.created_at)
    if tenant_id is not None:
        stmt = stmt.where(ActionOverride.tenant_id == tenant_id)
    return list(session.execute(stmt).scalars().all())
