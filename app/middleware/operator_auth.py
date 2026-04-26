"""Optional API key gate for operator routes (set OPERATOR_API_KEY in real environments)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class OperatorAuthMiddleware(BaseHTTPMiddleware):
    """
    Require X-Operator-Key when `Settings.operator_api_key` is configured.

    Keep every operator-facing router under these prefixes (see `app/main.py`):
    jobs, approvals, audit, email. Public: `/health`, `/chat`, OpenAPI docs.
    """

    PROTECTED_PREFIXES = ("/jobs", "/approvals", "/audit", "/email")

    async def dispatch(self, request: Request, call_next):
        from app.config import get_settings

        settings = get_settings()
        if not settings.operator_api_key:
            return await call_next(request)

        path = request.url.path
        if not any(path == prefix or path.startswith(prefix + "/") for prefix in self.PROTECTED_PREFIXES):
            return await call_next(request)

        if request.headers.get("X-Operator-Key") != settings.operator_api_key:
            return JSONResponse({"detail": "operator_key_required"}, status_code=401)

        return await call_next(request)
