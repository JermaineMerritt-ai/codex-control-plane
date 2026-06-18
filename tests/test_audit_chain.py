"""Tamper-evidence tests for the audit hash chain (PR 2).

These prove the chain links events, that mutating, reordering, deleting, or
inserting historical events breaks verification, and that the existing
single-arg `record()` contract still works (so the Gmail governed flow's audit
writes are unaffected).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from db.models import AuditEvent
from db.session import get_engine
from services.audit_service import (
    GENESIS_HASH,
    AuditAction,
    compute_event_hash,
    record,
    verify_chain,
)


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _seed(session, n: int) -> list[str]:
    ids = []
    for i in range(n):
        row = record(
            session,
            action=AuditAction.APPROVAL_CREATED,
            resource_type="approval",
            resource_id=f"appr-{i}",
            actor="op",
            metadata={"i": i},
        )
        ids.append(row.id)
    return ids


def test_chain_links_and_verifies_clean():
    factory = _factory()
    with factory() as session:
        _seed(session, 5)
    with factory() as session:
        rows = session.query(AuditEvent).order_by(AuditEvent.seq).all()
        assert [r.seq for r in rows] == [1, 2, 3, 4, 5]
        # First event roots at GENESIS; each subsequent links to the prior hash.
        assert rows[0].previous_hash == GENESIS_HASH
        for prev, cur in zip(rows, rows[1:]):
            assert cur.previous_hash == prev.event_hash
        result = verify_chain(session)
        assert result.status == "verified"
        assert result.ok is True
        assert result.verified_count == 5


def test_empty_chain_is_ok():
    factory = _factory()
    with factory() as session:
        result = verify_chain(session)
        assert result.status == "empty"
        assert result.ok is True


def test_mutating_old_event_breaks_verification():
    factory = _factory()
    with factory() as session:
        _seed(session, 4)
    # Tamper with an OLD event's content directly in the DB (bypassing record()).
    with factory() as session:
        session.execute(
            text("UPDATE audit_events SET reason = :r WHERE seq = :s"),
            {"r": "after-the-fact edit", "s": 2},
        )
        session.commit()
    with factory() as session:
        result = verify_chain(session)
        assert result.status == "failed"
        assert result.ok is False
        assert result.reason == "hash_mismatch"
        assert result.broken_at_seq == 2


def test_mutating_metadata_breaks_verification():
    factory = _factory()
    with factory() as session:
        _seed(session, 3)
    with factory() as session:
        session.execute(
            text("UPDATE audit_events SET metadata_json = :m WHERE seq = :s"),
            {"m": '{"i": 999}', "s": 1},
        )
        session.commit()
    with factory() as session:
        result = verify_chain(session)
        assert result.status == "failed"
        assert result.broken_at_seq == 1


def test_deleting_an_event_breaks_the_link():
    factory = _factory()
    with factory() as session:
        _seed(session, 5)
    with factory() as session:
        session.execute(text("DELETE FROM audit_events WHERE seq = :s"), {"s": 3})
        session.commit()
    with factory() as session:
        result = verify_chain(session)
        assert result.status == "failed"
        # seq 4 now follows seq 2, so its previous_hash no longer matches.
        assert result.reason == "broken_link"
        assert result.broken_at_seq == 4


def test_forged_event_with_recomputed_hash_still_breaks_chain():
    """Even if an attacker recomputes a forged event's own hash, the next
    event's previous_hash no longer matches, so the chain still breaks."""
    factory = _factory()
    with factory() as session:
        _seed(session, 4)
    with factory() as session:
        forged = session.query(AuditEvent).filter(AuditEvent.seq == 2).one()
        forged.reason = "forged"
        # Recompute a self-consistent hash for the forged row.
        forged.event_hash = compute_event_hash(forged, forged.previous_hash)
        session.commit()
    with factory() as session:
        result = verify_chain(session)
        assert result.status == "failed"
        # seq 2 verifies against itself now, but seq 3's link is stale.
        assert result.reason == "broken_link"
        assert result.broken_at_seq == 3


def test_record_backward_compatible_minimal_args():
    """The pre-PR2 call shape (no governance fields) still works and chains."""
    factory = _factory()
    with factory() as session:
        row = record(
            session,
            action=AuditAction.SEND_JOB_SUCCEEDED,
            resource_type="job",
            resource_id="job-1",
            metadata={"approval_id": "a1"},
        )
        assert row.id
        assert row.seq == 1
        assert row.previous_hash == GENESIS_HASH
        assert row.event_hash
        assert verify_chain(session).ok is True
