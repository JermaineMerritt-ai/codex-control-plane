"""Additive enterprise governance schema preparation for local/create_all deployments.

This repo does not yet use Alembic. PR 1 keeps the existing `create_all` path and
provides this optional additive migration helper for existing SQLite development
databases. It does not run automatically at application startup.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from db.governance_seed import (
    CONTROL_MAPPING_LANGUAGE,
    DEFAULT_TENANT_ID,
    DEFAULT_TENANT_NAME,
    INITIAL_CONTROL_FRAMEWORK_NAMES,
)
from db.models import Base


SQLITE_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "jobs": {"tenant_id": "VARCHAR(36)"},
    "approval_requests": {"tenant_id": "VARCHAR(36)"},
    "email_threads": {"tenant_id": "VARCHAR(36)"},
    "email_deliveries": {"tenant_id": "VARCHAR(36)"},
    "audit_events": {
        "tenant_id": "VARCHAR(36)",
        "actor_user_id": "VARCHAR(36)",
        "actor_type": "VARCHAR(64)",
        "action_type": "VARCHAR(64)",
        "policy_version": "VARCHAR(64)",
        "decision": "VARCHAR(64)",
        "reason": "TEXT",
        "previous_hash": "VARCHAR(64)",
        "event_hash": "VARCHAR(64)",
    },
}


def upgrade(engine: Engine) -> None:
    """Create new governance tables and add missing nullable columns for SQLite."""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _apply_sqlite_column_adds(engine)
    _seed_schema_reference_rows(engine)


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
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
        if "tenants" in existing_tables:
            conn.execute(
                text("INSERT OR IGNORE INTO tenants (id, name) VALUES (:id, :name)"),
                {"id": DEFAULT_TENANT_ID, "name": DEFAULT_TENANT_NAME},
            )
        for table_name in ("jobs", "approval_requests", "email_threads", "email_deliveries", "audit_events"):
            if table_name in existing_tables:
                conn.execute(
                    text(f"UPDATE {table_name} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
                    {"tenant_id": DEFAULT_TENANT_ID},
                )


def _seed_schema_reference_rows(engine: Engine) -> None:
    """Seed framework names only; no control certification or enforcement behavior."""
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            insert_sql = text(
                "INSERT OR IGNORE INTO control_frameworks (id, name, version, description) "
                "VALUES (:id, :name, 'current', :description)"
            )
        else:
            insert_sql = text(
                "INSERT INTO control_frameworks (id, name, version, description) "
                "VALUES (:id, :name, 'current', :description) "
                "ON CONFLICT (name, version) DO NOTHING"
            )
        for index, name in enumerate(INITIAL_CONTROL_FRAMEWORK_NAMES, start=1):
            conn.execute(
                insert_sql,
                {
                    "id": f"framework-seed-{index:02d}",
                    "name": name,
                    "description": CONTROL_MAPPING_LANGUAGE,
                },
            )
