"""Structured job result payloads (versioned shapes per job kind)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    """Reference to an output asset or related persisted record."""

    kind: str = Field(..., description="artifact or record type, e.g. approval_request")
    uri: str | None = None
    ref_id: str | None = Field(None, description="internal id when no blob URI exists")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatOrchestrateResult(BaseModel):
    """
    Standard result for `chat.orchestrate` jobs.

    Keeps a stable contract for dashboards and downstream automation.
    """

    kind: Literal["chat.orchestrate"] = "chat.orchestrate"
    status: Literal["completed", "blocked", "needs_approval"]
    summary: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    approval_required: bool
    next_action: str | None = None
    task_type: str = Field(
        default="general",
        description="Lightweight classification label (e.g. content_draft, outbound_message).",
    )
    policy_category: str = Field(
        default="draft_only",
        description="Policy bucket that governed this turn (see policy_service.PolicyCategory).",
    )
    approval_id: str | None = None
