"""Chat API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    tenant_id: str | None = None
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    max_steps: int = Field(default=8, ge=1, le=64)


class ChatResponse(BaseModel):
    job_id: str
    status: str
    message: str
