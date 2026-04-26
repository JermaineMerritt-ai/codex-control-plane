"""Policy guardrails: allowed, blocked, approval-gated."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PolicyCategory(str, Enum):
    read_only = "read_only"
    draft_only = "draft_only"
    outbound_send = "outbound_send"
    publish = "publish"
    destructive = "destructive"


@dataclass(frozen=True)
class PolicyEvaluation:
    category: PolicyCategory
    allowed: bool
    blocked: bool
    requires_approval: bool
    reason: str | None = None


# Substring match on lowercased user text. Kept in sync with email intent routing in
# `services/email_service.py` via this single export.
OUTBOUND_PHRASE_MARKERS: tuple[str, ...] = (
    "send email",
    "send an email",
    "send this email",
    "send the email",
    "send that email",
    "reply to all",
    "mail this",
)


def evaluate_action(category: PolicyCategory) -> PolicyEvaluation:
    """
    Return whether an action in `category` may proceed and whether approval is required.

    Rules are intentionally conservative defaults; refine per-tenant later.
    """
    if category is PolicyCategory.read_only:
        return PolicyEvaluation(category, allowed=True, blocked=False, requires_approval=False)
    if category is PolicyCategory.draft_only:
        return PolicyEvaluation(category, allowed=True, blocked=False, requires_approval=False)
    if category is PolicyCategory.outbound_send:
        return PolicyEvaluation(
            category,
            allowed=True,
            blocked=False,
            requires_approval=True,
            reason="Outbound send requires explicit approval.",
        )
    if category is PolicyCategory.publish:
        return PolicyEvaluation(
            category,
            allowed=True,
            blocked=False,
            requires_approval=True,
            reason="Publishing requires explicit approval.",
        )
    if category is PolicyCategory.destructive:
        return PolicyEvaluation(
            category,
            allowed=False,
            blocked=True,
            requires_approval=False,
            reason="Destructive actions are blocked by default.",
        )
    raise ValueError(f"unknown_policy_category:{category}")


def classify_message_policy_category(message: str) -> PolicyCategory:
    """Heuristic routing from user text to a policy bucket (stub classifier)."""
    text = message.lower()
    destructive_markers = ("delete ", "remove ", " wipe", "destroy ", "drop ")
    if any(m in text for m in destructive_markers):
        return PolicyCategory.destructive
    publish_markers = ("publish", "post to youtube", "go live", "upload video", "push to channel")
    if any(m in text for m in publish_markers):
        return PolicyCategory.publish
    if any(m in text for m in OUTBOUND_PHRASE_MARKERS):
        return PolicyCategory.outbound_send
    read_markers = ("list my emails", "fetch inbox", "read messages", "show thread")
    if any(m in text for m in read_markers):
        return PolicyCategory.read_only
    return PolicyCategory.draft_only
