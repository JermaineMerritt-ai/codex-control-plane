"""Additive migration for the human override registry (PR 16).

`action_overrides` is a new table, so create_all adds it on fresh databases and
this helper creates it on existing SQLite dev databases. No ALTER needed; no
Alembic/PostgreSQL workstream (deferred); not run at startup.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from db.models import Base


def upgrade(engine: Engine) -> None:
    # New table only — create_all creates action_overrides if missing and leaves
    # existing tables untouched.
    Base.metadata.create_all(bind=engine)
