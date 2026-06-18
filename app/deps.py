"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from services.rbac_service import Principal, resolve_principal
from services.tenant_service import InvalidApiKey, resolve_tenant_id

API_KEY_HEADER = "X-Api-Key"


def get_db(request: Request) -> Generator[Session, None, None]:
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
    finally:
        db.close()


def get_current_tenant_id(
    request: Request,
    db: Session = Depends(get_db),
) -> str | None:
    """Resolve the caller's tenant from the ``X-Api-Key`` header.

    Returns the bound tenant id for a valid key, or ``None`` for the
    operator/dev path (unscoped). A supplied-but-invalid key is rejected with
    401 — it must not fall through to full access.
    """
    api_key = request.headers.get(API_KEY_HEADER)
    try:
        return resolve_tenant_id(db, api_key=api_key)
    except InvalidApiKey as exc:
        raise HTTPException(status_code=401, detail="invalid_api_key") from exc


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> Principal:
    """Resolve the caller's RBAC principal (tenant + user + permissions).

    Invalid API key -> 401. No key -> operator/system bypass (unless hardened
    off). Valid key with no user -> no permissions (protected actions denied)."""
    api_key = request.headers.get(API_KEY_HEADER)
    try:
        return resolve_principal(db, api_key=api_key)
    except InvalidApiKey as exc:
        raise HTTPException(status_code=401, detail="invalid_api_key") from exc


def require_permission(permission: str) -> Callable[..., Principal]:
    """Dependency factory: 403 unless the principal holds ``permission``.

    RBAC is additive — it gates the route but never bypasses tenant isolation
    (callers still scope by ``principal.tenant_id``) or the approval gate."""

    def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise HTTPException(status_code=403, detail="permission_denied")
        return principal

    return _dependency
