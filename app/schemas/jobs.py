"""Job inspection API models."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from db.models import Job


class JobDetailResponse(BaseModel):
    id: str
    tenant_id: str | None
    type: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None


def split_stored_payload(payload_json: str | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Split DB `payload_json` into input payload vs optional `result` key."""
    if not payload_json:
        return {}, None
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        return {}, None
    data = dict(data)
    result = data.pop("result", None)
    if result is not None and not isinstance(result, dict):
        data["_result_non_object"] = result
        result = None
    return data, result


def job_to_detail(job: Job) -> JobDetailResponse:
    payload, result = split_stored_payload(job.payload_json)
    return JobDetailResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        type=job.type,
        status=job.status,
        attempts=job.attempts,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        payload=payload,
        result=result,
    )
