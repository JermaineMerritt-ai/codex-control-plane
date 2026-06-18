"""Append-only, tamper-evident audit trail for operator actions and job lifecycle.

PR 2 makes the audit trail a linked SHA-256 hash chain. Every event commits to
its immutable core fields **and** the previous event's hash, so altering,
reordering, inserting, or deleting any historical event breaks verification of
every event after it.

The chain is global and ordered by `seq`. `record()` remains the single write
path (used by the policy / approval / execution / delivery stages), so chaining
is automatic and the governed pipeline is unchanged. This module adds no tenant
enforcement and no RBAC — those are later PRs.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from db.models import AuditEvent

# Root of the chain. The first real event's `previous_hash` is GENESIS.
GENESIS_HASH = "0" * 64

# Concurrent writers compute `seq` from the current chain head; the UNIQUE
# constraint on `audit_events.seq` makes a racing duplicate fail at commit. The
# loser rolls back, re-reads the (now advanced) head, and retries. The bound is
# generous relative to realistic writer concurrency in the governed pipeline.
_MAX_RECORD_ATTEMPTS = 50


class AuditAction:
    APPROVAL_CREATED = "approval.created"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    SEND_JOB_ENQUEUED = "email.send_approved.enqueued"
    SEND_JOB_SUCCEEDED = "email.send_approved.succeeded"
    SEND_JOB_FAILED = "email.send_approved.failed"
    EVIDENCE_EXPORTED = "evidence.exported"


def _iso(value: datetime | None) -> str | None:
    """Canonicalize a datetime to a UTC ISO-8601 string.

    Naive datetimes (as SQLite returns) are assumed to be UTC. This guarantees
    the hash computed at write time matches the hash recomputed at verify time
    regardless of backend (SQLite drops tzinfo; Postgres keeps it).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _canonical_payload(
    *,
    seq: int | None,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant_id: str | None,
    actor: str | None,
    actor_user_id: str | None,
    actor_type: str | None,
    action_type: str | None,
    policy_version: str | None,
    decision: str | None,
    reason: str | None,
    metadata_json: str | None,
    created_at: datetime | None,
    previous_hash: str,
) -> str:
    """Deterministic JSON over the immutable core fields + previous_hash."""
    return json.dumps(
        {
            "seq": seq,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "tenant_id": tenant_id,
            "actor": actor,
            "actor_user_id": actor_user_id,
            "actor_type": actor_type,
            "action_type": action_type,
            "policy_version": policy_version,
            "decision": decision,
            "reason": reason,
            "metadata_json": metadata_json,
            "created_at": _iso(created_at),
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_event_hash(row: AuditEvent, previous_hash: str) -> str:
    """SHA-256 over the event's canonical payload bound to `previous_hash`."""
    payload = _canonical_payload(
        seq=row.seq,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        tenant_id=row.tenant_id,
        actor=row.actor,
        actor_user_id=row.actor_user_id,
        actor_type=row.actor_type,
        action_type=row.action_type,
        policy_version=row.policy_version,
        decision=row.decision,
        reason=row.reason,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
        previous_hash=previous_hash,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chain_head(session: Session) -> AuditEvent | None:
    """Most recent chained event (highest seq), or None for an empty chain."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_hash.is_not(None))
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def record(
    session: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant_id: str | None = None,
    actor: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor_user_id: str | None = None,
    actor_type: str | None = None,
    action_type: str | None = None,
    policy_version: str | None = None,
    decision: str | None = None,
    reason: str | None = None,
) -> AuditEvent:
    """Append a tamper-evident audit event to the chain.

    Backward compatible: existing callers pass action/resource_type/resource_id
    (+ optional tenant_id/actor/metadata). The descriptive governance fields are
    optional and, when supplied, are bound into the event hash.

    Concurrency-safe: the head read and the insert are not atomic, so two writers
    can compute the same `seq`. The UNIQUE constraint rejects the duplicate at
    commit; this loops, re-reading the advanced head, until the append succeeds.
    """
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
    last_error: Exception | None = None

    for attempt in range(_MAX_RECORD_ATTEMPTS):
        head = _chain_head(session)
        previous_hash = head.event_hash if head is not None else GENESIS_HASH
        next_seq = (head.seq + 1) if (head is not None and head.seq is not None) else 1

        row = AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            actor=actor,
            metadata_json=metadata_json,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action_type=action_type,
            policy_version=policy_version,
            decision=decision,
            reason=reason,
            seq=next_seq,
            previous_hash=previous_hash,
            # Set explicitly (UTC) so the value used in the hash is the value stored.
            created_at=datetime.now(timezone.utc),
        )
        row.event_hash = compute_event_hash(row, previous_hash)

        session.add(row)
        try:
            session.commit()
        except (IntegrityError, OperationalError) as exc:
            # Lost the race for this seq (or the DB was briefly locked).
            # Roll back, let the head advance, and retry with a fresh seq.
            session.rollback()
            last_error = exc
            time.sleep(0.005 * (attempt + 1))
            continue
        session.refresh(row)
        return row

    raise RuntimeError(
        f"audit record failed after {_MAX_RECORD_ATTEMPTS} attempts"
    ) from last_error


@dataclass(frozen=True)
class ChainVerificationResult:
    status: str  # "verified" | "failed" | "empty"
    verified_count: int
    total_count: int
    broken_at_seq: int | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("verified", "empty")


def verify_chain(session: Session) -> ChainVerificationResult:
    """Recompute and re-link the entire global chain.

    Returns the first break (if any): a `broken_link` when an event's
    `previous_hash` does not match the prior event's `event_hash`, or a
    `hash_mismatch` when an event's stored hash does not match a recomputation
    of its own contents. Legacy pre-chain rows (no `event_hash`) are skipped.
    """
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_hash.is_not(None))
        .order_by(AuditEvent.seq)
    )
    rows = list(session.execute(stmt).scalars().all())
    if not rows:
        return ChainVerificationResult(status="empty", verified_count=0, total_count=0)

    expected_previous = GENESIS_HASH
    for index, row in enumerate(rows):
        if row.previous_hash != expected_previous:
            return ChainVerificationResult(
                status="failed",
                verified_count=index,
                total_count=len(rows),
                broken_at_seq=row.seq,
                reason="broken_link",
            )
        if compute_event_hash(row, row.previous_hash) != row.event_hash:
            return ChainVerificationResult(
                status="failed",
                verified_count=index,
                total_count=len(rows),
                broken_at_seq=row.seq,
                reason="hash_mismatch",
            )
        expected_previous = row.event_hash

    return ChainVerificationResult(
        status="verified",
        verified_count=len(rows),
        total_count=len(rows),
    )


def list_audit_events(
    session: Session,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(limit, 500))
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    return list(session.execute(stmt).scalars().all())


def list_for_resource(session: Session, *, resource_type: str, resource_id: str) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.resource_type == resource_type, AuditEvent.resource_id == resource_id)
        .order_by(AuditEvent.created_at)
    )
    return list(session.execute(stmt).scalars().all())
