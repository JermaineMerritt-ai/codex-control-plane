"""Phase 1 packaging tests (PR 8): procurement-safe doc language + demo helper.

Docs/demo only — no core behavior. These guard the buyer-facing language and
prove the demo helper produces a real packet using existing services.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from db.session import get_engine
from scripts.demo_evidence_packet import build_demo_packet

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"

NEW_DOCS = [
    "ENTERPRISE_GOVERNANCE_FOUNDATION.md",
    "BUYER_AUDIT_PACKET_DEMO.md",
    "PHASE_1_COMPLETION_SUMMARY.md",
]

FORBIDDEN = (
    "guarantees compliance",
    "certifies compliance",
    "fully compliant",
    "guaranteed compliance",
    "compliance certification",
    "regulatory approval",
)

APPROVED_MARKERS = ("audit readiness", "evidence collection", "governance workflows")


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def test_new_docs_exist():
    for name in NEW_DOCS:
        assert (DOCS_DIR / name).is_file(), f"missing doc: {name}"


def test_new_docs_use_procurement_safe_language():
    for name in NEW_DOCS:
        # Collapse whitespace so hard-wrapped line breaks don't split phrases
        # (e.g. "governance\nworkflows") for either the forbidden or marker check.
        text = " ".join((DOCS_DIR / name).read_text(encoding="utf-8").lower().split())
        for phrase in FORBIDDEN:
            assert phrase not in text, f"{name} contains forbidden phrase: {phrase!r}"
        # Each buyer-facing doc carries the approved supportive language.
        assert "support" in text
        assert all(marker in text for marker in APPROVED_MARKERS), name


def test_demo_helper_builds_a_complete_packet():
    with _factory()() as s:
        packet = build_demo_packet(s)
    assert packet is not None
    assert packet["packet_type"] == "governed_action"
    assert packet["audit_chain_verification"]["status"] == "verified"
    assert packet["evidence_gaps"] == []  # complete demo chain -> no gaps
    assert len(packet["mapped_controls"]) >= 1
    assert len(packet["evidence_artifacts"]) == 1
