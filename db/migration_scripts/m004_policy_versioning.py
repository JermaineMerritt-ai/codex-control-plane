"""Additive migration for policy versioning (PR 15).

Adds lifecycle/provenance columns to governance_policies and the policy_version_id
binding to governed_actions. Same additive, SQLite-only, optional pattern as
m001-m003 — fresh DBs get the columns via create_all; no Alembic/PostgreSQL
workstream (deferred); not run at startup.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from db.models import Base

SQLITE_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "governance_policies": {
        "status": "VARCHAR(32)",
        "effective_from": "DATETIME",
        "effective_to": "DATETIME",
        "created_by_user_id": "VARCHAR(36)",
        "approved_by_user_id": "VARCHAR(36)",
        "change_reason": "TEXT",
    },
    "governed_actions": {
        "policy_version_id": "VARCHAR(36)",
    },
}


def upgrade(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _apply_sqlite_column_adds(engine)


def _apply_sqlite_column_adds(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table_name, columns in SQLITE_ADDITIVE_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
        if "governance_policies" in existing_tables:
            conn.execute(
                text("UPDATE governance_policies SET status = 'active' "
                     "WHERE status IS NULL AND is_active = 1")
            )
            conn.execute(
                text("UPDATE governance_policies SET status = 'draft' WHERE status IS NULL")
            )
