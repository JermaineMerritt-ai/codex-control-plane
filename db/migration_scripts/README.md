# Migration Scripts

The repo currently uses SQLAlchemy `create_all` and does not include Alembic.

PR 1 adds `m001_enterprise_governance_schema.py` as a repo-compatible additive migration helper for existing SQLite development databases. It creates new schema objects, adds missing nullable preparation columns, backfills a default development tenant for existing rows, and seeds initial control framework names only.

The helper is not called automatically at application startup. Runtime enforcement, RBAC checks, audit hash chaining, and evidence export are intentionally deferred to later PRs.
