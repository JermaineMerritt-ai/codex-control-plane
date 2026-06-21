"""Additive migration for evidence packet persistence (PR 14).

Adds packet_hash / version / retention_status to evidence_packets. Same optional,
additive, SQLite-only pattern as m001/m002 — fresh DBs get the columns via
create_all; this helper backfills existing SQLite dev databases. No Alembic /
PostgreSQL workstream (deferred); not run at startup.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from db.models import Base

SQLITE_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "evidence_packets": {
        "packet_hash": "VARCHAR(64)",
        "version": "INTEGER",
        "retention_status": "VARCHAR(32)",
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
        # Backfill retention_status for any pre-existing rows.
        if "evidence_packets" in existing_tables:
            conn.execute(
                text("UPDATE evidence_packets SET retention_status = 'active' WHERE retention_status IS NULL")
            )
