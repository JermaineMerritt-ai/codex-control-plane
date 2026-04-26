"""FastAPI control plane entrypoint: routes wire to services; no heavy work inline."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.email import router as email_router
from app.api.jobs import router as jobs_router
from app.middleware.operator_auth import OperatorAuthMiddleware
from app.deps import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from db.session import get_engine, get_session_factory, init_db
from services.job_service import create_job
from services.job_types import CHAT_ORCHESTRATE


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import get_settings

    get_settings()
    engine = get_engine()
    init_db(engine)
    app.state.session_factory = get_session_factory(engine)
    yield
    engine.dispose()


app = FastAPI(
    title="codex-control-plane",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(OperatorAuthMiddleware)

app.include_router(jobs_router)
app.include_router(approvals_router)
app.include_router(audit_router)
app.include_router(email_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    """Accept chat input, persist a durable job, return immediately (no inline orchestration)."""
    job = create_job(
        db,
        job_type=CHAT_ORCHESTRATE,
        tenant_id=body.tenant_id,
        payload={
            "session_id": body.session_id,
            "message": body.message,
            "max_steps": body.max_steps,
        },
    )
    return ChatResponse(
        job_id=job.id,
        status="queued",
        message="Chat request accepted",
    )
