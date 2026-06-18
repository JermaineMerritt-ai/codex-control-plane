"""Tenant resolution and API-key binding (PR 3 — tenant isolation).

Tenant context is derived from the caller's *credential*, never from a
client-supplied field, so a caller cannot choose to read another tenant's data:

- A valid API key resolves to exactly the tenant it was provisioned for.
- No API key (the operator/dev fallback, and the system worker) resolves to
  ``None`` = unscoped full access, which preserves the existing single-tenant
  demo and background worker unchanged.

This module adds **tenant** binding only. Roles and permissions (RBAC) are a
later PR; the operator key remains full-access for now.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ApiKey, Tenant


class InvalidApiKey(Exception):
    """Raised when an API key is supplied but does not match an active key."""


def hash_api_key(raw_key: str) -> str:
    """Stable, non-reversible fingerprint stored in ``api_keys.key_hash``."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def get_tenant(session: Session, tenant_id: str) -> Tenant | None:
    return session.get(Tenant, tenant_id)


def provision_api_key(
    session: Session,
    *,
    tenant_id: str,
    name: str,
    raw_key: str,
    user_id: str | None = None,
) -> ApiKey:
    """Create an API key bound to a tenant. Only the hash is stored."""
    row = ApiKey(
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        key_hash=hash_api_key(raw_key),
        is_active=True,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def resolve_tenant_id(session: Session, *, api_key: str | None) -> str | None:
    """Resolve the caller's tenant from an API key.

    Returns the bound ``tenant_id`` for a valid key, or ``None`` when no key is
    presented (operator/dev/system path = unscoped). Raises ``InvalidApiKey``
    when a key is presented but unknown/inactive — a bad key must never silently
    fall back to full access.
    """
    if not api_key:
        return None
    stmt = select(ApiKey).where(
        ApiKey.key_hash == hash_api_key(api_key),
        ApiKey.is_active.is_(True),
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise InvalidApiKey("invalid_api_key")
    row.last_used_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return row.tenant_id
