"""Additive migration for the tamper-evident audit hash chain (PR 2).

PR 1 (m001) added the `previous_hash` / `event_hash` columns. PR 2 adds the
`seq` ordering column and otherwise relies on `create_all` for fresh databases.
Like m001, this helper is optional, does not run at startup, and only adds
nullable columns so existing rows and the running demo are unaffected.

Legacy rows created before chaining have `seq`/`event_hash` = NULL and are
skipped by `verify_chain`; the chain begins at the first chained event.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from db.models import Base


SQLITE_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "audit_events": {"seq": "INTEGER"},
}


def upgrade(engine: Engine) -> None:
    """Create any missing tables and add the nullable `seq` column for SQLite."""
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
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
        # UNIQUE index on seq prevents two concurrent writers from forking the
        # chain at the same position. NULLs are distinct, so legacy rows (seq
        # NULL after the column add) do not collide.
        if "audit_events" in existing_tables:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_events_seq "
                    "ON audit_events (seq)"
                )
            )
