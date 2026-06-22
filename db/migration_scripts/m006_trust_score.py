"""Additive migration for trust scores (PR 18, Trust Score v0).

`trust_scores` is a new table, so create_all adds it on fresh databases and this
helper creates it on existing SQLite dev databases. No ALTER needed; no
Alembic/PostgreSQL workstream (deferred); not run at startup.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from db.models import Base


def upgrade(engine: Engine) -> None:
    # New table only — create_all creates trust_scores if missing and leaves
    # existing tables untouched.
    Base.metadata.create_all(bind=engine)
