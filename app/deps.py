"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

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
