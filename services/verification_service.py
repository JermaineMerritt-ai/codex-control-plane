"""Procurement verification lifecycle (PR 21).

A reviewable lifecycle over a governed subject that **consumes existing artifacts**
— the subject's signed evidence packet (must verify `valid`) and its trust score
(must meet a required minimum). It does not re-derive evidence or scores.

States: requested -> under_review -> approved -> revoked, with rejected reachable
from review (bad evidence) . Every transition is audited. Verification supports
procurement validation; it is not a certification or guarantee of compliance.

Errors are raised as ValueError with a stable code; the API maps codes to HTTP:
  subject_not_found / verification_not_found  -> 404
  no_signed_evidence                          -> 422
  invalid_transition                          -> 409
  evidence_not_valid:<status>                 -> 422
  insufficient_trust_score                    -> 422
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import EvidencePacket, TrustVerification
from services import (
    audit_service,
    evidence_graph,
    evidence_signature_service,
    evidence_store,
    trust_score_service,
)

DEFAULT_MIN_SCORE = 60
SUBJECT_GOVERNED_ACTION = "governed_action"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(session: Session, *, action: str, row: TrustVerification, actor: str | None, **meta: Any) -> None:
    audit_service.record(
        session,
        action=action,
        resource_type="trust_verification",
        resource_id=row.id,
        tenant_id=row.tenant_id,
        actor=actor,
        metadata={"status": row.status, "subject_id": row.subject_id, **meta},
    )


def get_verification(
    session: Session, verification_id: str, *, tenant_id: str | None = None
) -> TrustVerification | None:
    row = session.get(TrustVerification, verification_id)
    if row is None:
        return None
    if tenant_id is not None and row.tenant_id != tenant_id:
        return None  # cross-tenant -> not found (non-leaking)
    return row


def _latest_signed_packet(
    session: Session, *, tenant_id: str | None, subject_id: str
) -> EvidencePacket | None:
    stmt = (
        select(EvidencePacket)
        .where(
            EvidencePacket.scope_type == SUBJECT_GOVERNED_ACTION,
            EvidencePacket.scope_id == subject_id,
            EvidencePacket.packet_signature.is_not(None),
        )
        .order_by(EvidencePacket.version.desc())
    )
    if tenant_id is not None:
        stmt = stmt.where(EvidencePacket.tenant_id == tenant_id)
    return session.execute(stmt).scalars().first()


def request_verification(
    session: Session,
    *,
    tenant_id: str | None,
    subject_id: str,
    requested_by: str | None,
    subject_type: str = SUBJECT_GOVERNED_ACTION,
    min_score_required: int = DEFAULT_MIN_SCORE,
) -> TrustVerification:
    """Open a verification for a governed subject that has signed evidence."""
    # Validate the subject exists in this tenant (reuses the governance graph).
    graph = evidence_graph.get_evidence_graph(
        session, governed_action_id=subject_id, tenant_id=tenant_id
    )
    if graph is None:
        raise ValueError("subject_not_found")
    packet = _latest_signed_packet(session, tenant_id=tenant_id, subject_id=subject_id)
    if packet is None:
        raise ValueError("no_signed_evidence")

    row = TrustVerification(
        tenant_id=tenant_id,
        subject_type=subject_type,
        subject_id=subject_id,
        status="requested",
        evidence_packet_id=packet.id,
        min_score_required=min_score_required,
        requested_by_user_id=requested_by,
    )
    session.add(row)
    session.commit()
    _audit(session, action="verification.requested", row=row, actor=requested_by,
           evidence_packet_id=packet.id, min_score_required=min_score_required)
    return row


def _evidence_status(session: Session, row: TrustVerification) -> dict[str, Any]:
    packet = (
        evidence_store.get_packet(session, row.evidence_packet_id, tenant_id=row.tenant_id)
        if row.evidence_packet_id
        else None
    )
    if packet is None:
        return {"status": "missing", "reasons": ["referenced evidence packet not found"]}
    return evidence_signature_service.verify_packet(packet)


def review_verification(
    session: Session,
    *,
    verification_id: str,
    tenant_id: str | None,
    reviewed_by: str | None,
    notes: str | None = None,
) -> tuple[TrustVerification, dict[str, Any]]:
    """requested -> under_review, unless the evidence is not valid (-> rejected)."""
    row = get_verification(session, verification_id, tenant_id=tenant_id)
    if row is None:
        raise ValueError("verification_not_found")
    if row.status != "requested":
        raise ValueError("invalid_transition")

    ev = _evidence_status(session, row)
    row.reviewed_by_user_id = reviewed_by
    row.review_notes = notes
    row.reviewed_at = _now()
    if ev["status"] == "valid":
        row.status = "under_review"
        row.decision_reason = None
    else:
        # Bad evidence holds the verification out of the approvable path.
        row.status = "rejected"
        row.decision_reason = f"evidence_{ev['status']}"
    session.add(row)
    session.commit()
    _audit(session, action="verification.reviewed", row=row, actor=reviewed_by,
           evidence_status=ev["status"])
    return row, ev


def approve_verification(
    session: Session,
    *,
    verification_id: str,
    tenant_id: str | None,
    approved_by: str | None,
) -> tuple[TrustVerification, dict[str, Any]]:
    """under_review -> approved, only if evidence is valid AND trust score meets the
    required minimum. Otherwise raises (status unchanged)."""
    row = get_verification(session, verification_id, tenant_id=tenant_id)
    if row is None:
        raise ValueError("verification_not_found")
    if row.status != "under_review":
        raise ValueError("invalid_transition")

    ev = _evidence_status(session, row)
    if ev["status"] != "valid":
        raise ValueError(f"evidence_not_valid:{ev['status']}")

    score = trust_score_service.score_action(
        session, governed_action_id=row.subject_id, tenant_id=tenant_id
    )
    if score is None:
        raise ValueError("subject_not_found")
    if score["score"] < row.min_score_required:
        raise ValueError("insufficient_trust_score")

    row.status = "approved"
    row.decided_by_user_id = approved_by
    row.decided_at = _now()
    row.trust_score = score["score"]
    row.trust_score_id = score.get("score_id")
    row.decision_reason = "approved"
    session.add(row)
    session.commit()
    _audit(session, action="verification.approved", row=row, actor=approved_by,
           trust_score=score["score"], min_score_required=row.min_score_required)
    return row, score


def revoke_verification(
    session: Session,
    *,
    verification_id: str,
    tenant_id: str | None,
    revoked_by: str | None,
    reason: str,
) -> TrustVerification:
    """approved -> revoked."""
    row = get_verification(session, verification_id, tenant_id=tenant_id)
    if row is None:
        raise ValueError("verification_not_found")
    if row.status != "approved":
        raise ValueError("invalid_transition")
    row.status = "revoked"
    row.decided_by_user_id = revoked_by
    row.decided_at = _now()
    row.decision_reason = reason
    session.add(row)
    session.commit()
    _audit(session, action="verification.revoked", row=row, actor=revoked_by, reason=reason)
    return row
