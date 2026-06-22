"""Evidence packet signing & verification (PR 20).

Extends the existing persisted `EvidencePacket` (PR 14) with authenticity: an
Ed25519 signature over a payload that binds the packet's identity, version, and
content hash. Verification is procurement-safe and explainable — it returns one of
`valid | expired | revoked | tampered | unsigned` with human-readable reasons, and
publishes the public key so a third party can verify independently.

NON-PRODUCTION / pilot-grade signing. This uses a single Ed25519 key (from
settings, or a fixed, publicly-known PILOT key if unset). It is for evaluation
only and is NOT production-grade signing: managed key storage (KMS/HSM), key
rotation, and external audit anchoring are NOT implemented yet and are deferred.
Until that work lands, do not represent these signatures as production-grade.
Signatures support evidence verification; they are not a certification or
guarantee of compliance.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import EvidencePacket
from services import audit_service, evidence_store

ALGORITHM = "Ed25519"

# NON-PRODUCTION fixed PILOT seed, used only when no signing key is configured.
# This value is committed to source and therefore PUBLICLY KNOWN — anyone can forge
# signatures under it. It exists solely so evaluation demos are reproducible. It is
# NOT a production key; replace it with a managed key (settings.evidence_signing_key,
# 64-char hex) backed by KMS/HSM + rotation before any real or hosted deployment.
_PILOT_SEED_HEX = "00" * 31 + "01"


def _seed_bytes() -> bytes:
    raw = (get_settings().evidence_signing_key or _PILOT_SEED_HEX).strip()
    try:
        seed = bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError("evidence_signing_key must be 64-char hex (32 bytes)") from exc
    if len(seed) != 32:
        raise ValueError("evidence_signing_key must decode to exactly 32 bytes")
    return seed


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes())


def _public_key() -> Ed25519PublicKey:
    return _private_key().public_key()


def public_key_hex() -> str:
    """Publish this so a third party can verify a packet signature independently."""
    from cryptography.hazmat.primitives import serialization

    return _public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive timestamps (SQLite) as UTC for comparison."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def signing_payload(packet_id: str, version: int | None, packet_hash: str | None) -> bytes:
    """Deterministic bytes the signature commits to (identity + version + content)."""
    return f"{packet_id}:{version}:{packet_hash}".encode("utf-8")


def sign_packet(
    session: Session,
    *,
    packet: EvidencePacket,
    signed_by: str | None = None,
    ttl_days: int | None = None,
    record_audit: bool = True,
) -> EvidencePacket:
    """Sign a persisted packet over its hash; set signed_at/expires_at. Idempotent
    re-sign overwrites the prior signature (e.g. after key rotation)."""
    ttl = get_settings().evidence_packet_ttl_days if ttl_days is None else ttl_days
    signature = _private_key().sign(
        signing_payload(packet.id, packet.version, packet.packet_hash)
    )
    packet.packet_signature = signature.hex()
    packet.signature_algorithm = ALGORITHM
    packet.signed_at = _now()
    packet.expires_at = _now() + timedelta(days=ttl)
    session.add(packet)
    session.commit()
    if record_audit:
        audit_service.record(
            session,
            action="evidence.packet.signed",
            resource_type="evidence_packet",
            resource_id=packet.id,
            tenant_id=packet.tenant_id,
            actor=signed_by,
            metadata={"algorithm": ALGORITHM, "version": packet.version,
                      "packet_hash": packet.packet_hash, "expires_at": packet.expires_at.isoformat()},
        )
    return packet


def revoke_packet(
    session: Session,
    *,
    packet: EvidencePacket,
    reason: str,
    revoked_by: str | None = None,
) -> EvidencePacket:
    """Mark a packet revoked (does not delete it; verification will report revoked)."""
    packet.revoked_at = _now()
    packet.revocation_reason = reason
    session.add(packet)
    session.commit()
    audit_service.record(
        session,
        action="evidence.packet.revoked",
        resource_type="evidence_packet",
        resource_id=packet.id,
        tenant_id=packet.tenant_id,
        actor=revoked_by,
        metadata={"reason": reason, "version": packet.version},
    )
    return packet


def _signature_ok(packet: EvidencePacket) -> bool:
    if not packet.packet_signature:
        return False
    try:
        _public_key().verify(
            bytes.fromhex(packet.packet_signature),
            signing_payload(packet.id, packet.version, packet.packet_hash),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _content_intact(packet: EvidencePacket) -> bool:
    """Recompute the hash from the stored export and compare to the stored hash."""
    if not packet.json_export or not packet.packet_hash:
        return False
    try:
        recomputed = evidence_store.compute_packet_hash(json.loads(packet.json_export))
    except (ValueError, TypeError):
        return False
    return recomputed == packet.packet_hash


def verify_packet(packet: EvidencePacket) -> dict[str, Any]:
    """Explainable verification. Status precedence: tampered > revoked > expired >
    valid; unsigned if never signed."""
    reasons: list[str] = []
    base = {
        "packet_id": packet.id,
        "version": packet.version,
        "packet_hash": packet.packet_hash,
        "algorithm": packet.signature_algorithm,
        "signed_at": packet.signed_at.isoformat() if packet.signed_at else None,
        "expires_at": packet.expires_at.isoformat() if packet.expires_at else None,
        "revoked_at": packet.revoked_at.isoformat() if packet.revoked_at else None,
        "public_key": public_key_hex(),
    }

    if not packet.packet_signature:
        return {**base, "status": "unsigned",
                "reasons": ["packet has not been signed"]}

    content_ok = _content_intact(packet)
    sig_ok = _signature_ok(packet)
    if not content_ok:
        reasons.append("stored packet content does not match its recorded hash")
    if not sig_ok:
        reasons.append("signature does not verify against the published public key")
    if not (content_ok and sig_ok):
        return {**base, "status": "tampered", "reasons": reasons}

    if packet.revoked_at is not None:
        return {**base, "status": "revoked",
                "reasons": [f"revoked: {packet.revocation_reason or 'no reason recorded'}"]}

    expires = _aware(packet.expires_at)
    if expires is not None and _now() > expires:
        return {**base, "status": "expired",
                "reasons": [f"signature expired at {expires.isoformat()}"]}

    return {**base, "status": "valid",
            "reasons": ["signature verified and content intact"]}
