"""Persisted evidence packets (PR 14 — pilot persistence only).

Saves the output of the existing on-demand packet builder so packets are
versioned, hash-stamped, and retrievable, and records audit events when a packet
is generated or downloaded. No new packet engine; no Alembic/Postgres workstream.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import EvidencePacket
from services import audit_service, evidence_packet


def compute_packet_hash(packet: dict[str, Any]) -> str:
    """SHA-256 over the packet's content, excluding the volatile generation time."""
    core = {k: v for k, v in packet.items() if k != "generated_at"}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _scoped(row: EvidencePacket | None, tenant_id: str | None) -> EvidencePacket | None:
    if row is None:
        return None
    if tenant_id is not None and row.tenant_id != tenant_id:
        return None
    return row


def persist_packet(
    session: Session,
    *,
    tenant_id: str | None,
    packet: dict[str, Any],
    generated_by: str | None = None,
) -> EvidencePacket:
    """Store a built packet as a new version for its scope; supersede the prior
    active version; record an `evidence.packet.generated` audit event."""
    scope_type = packet.get("packet_type", "governed_action")
    scope_id = packet.get("scope_id")

    stmt = select(EvidencePacket).where(
        EvidencePacket.scope_type == scope_type, EvidencePacket.scope_id == scope_id
    )
    if tenant_id is not None:
        stmt = stmt.where(EvidencePacket.tenant_id == tenant_id)
    existing = list(session.execute(stmt).scalars().all())
    version = (max((p.version or 0) for p in existing) + 1) if existing else 1
    for prior in existing:
        if prior.retention_status == "active":
            prior.retention_status = "superseded"
            session.add(prior)

    row = EvidencePacket(
        tenant_id=tenant_id,
        scope_type=scope_type,
        scope_id=scope_id,
        summary_json=json.dumps(packet, default=str),
        json_export=evidence_packet.render_json(packet),
        markdown_export=evidence_packet.render_markdown(packet),
        created_by_user_id=generated_by,
        packet_hash=compute_packet_hash(packet),
        version=version,
        retention_status="active",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    audit_service.record(
        session,
        action="evidence.packet.generated",
        resource_type="evidence_packet",
        resource_id=row.id,
        tenant_id=tenant_id,
        actor=generated_by,
        metadata={"scope_type": scope_type, "scope_id": scope_id,
                  "version": version, "packet_hash": row.packet_hash},
    )
    # Sign the persisted packet so it is verifiable (PR 20). Lazy import avoids a
    # module cycle (the signature service depends on this module's hash helper).
    from services import evidence_signature_service

    evidence_signature_service.sign_packet(session, packet=row, signed_by=generated_by)
    return row


def get_packet(session: Session, packet_id: str, *, tenant_id: str | None = None) -> EvidencePacket | None:
    return _scoped(session.get(EvidencePacket, packet_id), tenant_id)


def list_packets(
    session: Session, *, tenant_id: str | None = None, scope_id: str | None = None
) -> list[EvidencePacket]:
    stmt = select(EvidencePacket).order_by(EvidencePacket.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(EvidencePacket.tenant_id == tenant_id)
    if scope_id is not None:
        stmt = stmt.where(EvidencePacket.scope_id == scope_id)
    return list(session.execute(stmt).scalars().all())


def record_download(
    session: Session,
    *,
    packet: EvidencePacket,
    fmt: str,
    tenant_id: str | None = None,
    downloaded_by: str | None = None,
) -> None:
    """Record an `evidence.packet.downloaded` audit event for a stored packet."""
    audit_service.record(
        session,
        action="evidence.packet.downloaded",
        resource_type="evidence_packet",
        resource_id=packet.id,
        tenant_id=tenant_id,
        actor=downloaded_by,
        metadata={"format": fmt, "version": packet.version, "packet_hash": packet.packet_hash},
    )
