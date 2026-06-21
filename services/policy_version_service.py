"""Policy versioning registry + binding (PR 15 — pilot scope).

A registry/lifecycle layer over GovernancePolicy, NOT a new rules engine. Each
governed action binds immutably to the exact policy version in effect; evaluation
logic stays in policy_service. Lifecycle: draft -> active -> superseded.

Rollback is **forward-only**: "activate a previous version" supersedes the
current active one. It never rewrites historical governed actions or mutates a
prior decision — bound `policy_version_id`s are immutable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import GovernancePolicy
from services import audit_service

DEFAULT_POLICY_NAME = "ai_vendor_governance"


def _scoped(row: GovernancePolicy | None, tenant_id: str | None) -> GovernancePolicy | None:
    if row is None:
        return None
    if tenant_id is not None and row.tenant_id != tenant_id:
        return None
    return row


def get_version(session: Session, version_id: str, *, tenant_id: str | None = None) -> GovernancePolicy | None:
    return _scoped(session.get(GovernancePolicy, version_id), tenant_id)


def list_versions(
    session: Session, *, tenant_id: str | None = None, name: str | None = None
) -> list[GovernancePolicy]:
    stmt = select(GovernancePolicy).order_by(GovernancePolicy.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(GovernancePolicy.tenant_id == tenant_id)
    if name is not None:
        stmt = stmt.where(GovernancePolicy.name == name)
    return list(session.execute(stmt).scalars().all())


def _active_versions(session: Session, tenant_id: str | None, name: str) -> list[GovernancePolicy]:
    stmt = select(GovernancePolicy).where(
        GovernancePolicy.name == name, GovernancePolicy.status == "active"
    )
    # tenant_id may be None (system default) — match exactly that value.
    stmt = stmt.where(GovernancePolicy.tenant_id == tenant_id) if tenant_id is not None else \
        stmt.where(GovernancePolicy.tenant_id.is_(None))
    return list(session.execute(stmt).scalars().all())


def get_active(session: Session, *, tenant_id: str | None, name: str = DEFAULT_POLICY_NAME) -> GovernancePolicy | None:
    """Active version for (tenant, name); falls back to the system default
    (tenant_id IS NULL) when the tenant has none."""
    active = _active_versions(session, tenant_id, name)
    if active:
        return active[0]
    if tenant_id is not None:
        system = _active_versions(session, None, name)
        if system:
            return system[0]
    return None


def create_version(
    session: Session,
    *,
    tenant_id: str | None,
    name: str = DEFAULT_POLICY_NAME,
    version: str,
    rules: dict[str, Any] | None = None,
    created_by: str | None = None,
    change_reason: str | None = None,
) -> GovernancePolicy:
    """Create a draft policy version (not active until activated)."""
    row = GovernancePolicy(
        tenant_id=tenant_id,
        name=name,
        version=version,
        rules_json=json.dumps(rules) if rules else None,
        is_active=False,
        status="draft",
        created_by_user_id=created_by,
        change_reason=change_reason,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_service.record(
        session, action="policy.version.created", resource_type="policy_version",
        resource_id=row.id, tenant_id=tenant_id, actor=created_by,
        metadata={"name": name, "version": version},
    )
    return row


def activate(
    session: Session, *, version_id: str, approved_by: str | None = None, tenant_id: str | None = None
) -> GovernancePolicy:
    """Make a version active; supersede the prior active version for (tenant, name)."""
    pol = get_version(session, version_id, tenant_id=tenant_id)
    if pol is None:
        raise ValueError("policy_version_not_found")
    now = datetime.now(timezone.utc)
    for other in _active_versions(session, pol.tenant_id, pol.name):
        if other.id != pol.id:
            other.status = "superseded"
            other.is_active = False
            other.effective_to = now
            session.add(other)
    pol.status = "active"
    pol.is_active = True
    pol.effective_from = now
    pol.effective_to = None
    if approved_by:
        pol.approved_by_user_id = approved_by
    session.add(pol)
    session.commit()
    session.refresh(pol)
    audit_service.record(
        session, action="policy.version.activated", resource_type="policy_version",
        resource_id=pol.id, tenant_id=pol.tenant_id, actor=approved_by,
        metadata={"name": pol.name, "version": pol.version},
    )
    return pol


def rollback_to(
    session: Session, *, version_id: str, approved_by: str | None = None,
    change_reason: str | None = None, tenant_id: str | None = None,
) -> GovernancePolicy:
    """Roll back by **activating a previous version** (forward-only). Supersedes
    the current active version. Does NOT rewrite historical actions or mutate
    prior decisions — only the registry's active pointer moves."""
    pol = get_version(session, version_id, tenant_id=tenant_id)
    if pol is None:
        raise ValueError("policy_version_not_found")
    activated = activate(session, version_id=version_id, approved_by=approved_by, tenant_id=tenant_id)
    audit_service.record(
        session, action="policy.version.rolled_back", resource_type="policy_version",
        resource_id=activated.id, tenant_id=activated.tenant_id, actor=approved_by,
        metadata={"name": activated.name, "version": activated.version,
                  "change_reason": change_reason, "mode": "activate_previous"},
    )
    return activated


def seed_default_policy(session: Session) -> GovernancePolicy:
    """Idempotently ensure a system-default ACTIVE policy version exists so the
    workflow always binds to a real version."""
    existing = session.execute(
        select(GovernancePolicy).where(
            GovernancePolicy.tenant_id.is_(None),
            GovernancePolicy.name == DEFAULT_POLICY_NAME,
            GovernancePolicy.version == "v1",
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status != "active":
            existing.status = "active"
            existing.is_active = True
            if existing.effective_from is None:
                existing.effective_from = datetime.now(timezone.utc)
            session.add(existing)
            session.commit()
        return existing
    row = GovernancePolicy(
        tenant_id=None,
        name=DEFAULT_POLICY_NAME,
        version="v1",
        is_active=True,
        status="active",
        effective_from=datetime.now(timezone.utc),
        change_reason="Initial system default policy version.",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
