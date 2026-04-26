"""Operator-facing email / delivery inspection models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from db.models import EmailDeliveryRecord


class EmailDeliveryDetailResponse(BaseModel):
    id: str
    tenant_id: str | None
    thread_external_id: str
    gmail_draft_id: str | None
    gmail_message_id: str | None
    approval_id: str | None
    source_job_id: str | None
    execution_job_id: str | None
    status: str
    last_error: str | None
    updated_at: datetime


class EmailDeliveryListResponse(BaseModel):
    items: list[EmailDeliveryDetailResponse] = Field(default_factory=list)


class ThreadSummaryResponse(BaseModel):
    thread: dict[str, Any] | None
    deliveries: list[dict[str, Any]]


def delivery_to_detail(row: EmailDeliveryRecord) -> EmailDeliveryDetailResponse:
    return EmailDeliveryDetailResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        thread_external_id=row.thread_external_id,
        gmail_draft_id=row.gmail_draft_id,
        gmail_message_id=row.gmail_message_id,
        approval_id=row.approval_id,
        source_job_id=row.source_job_id,
        execution_job_id=row.execution_job_id,
        status=row.status,
        last_error=row.last_error,
        updated_at=row.updated_at,
    )
