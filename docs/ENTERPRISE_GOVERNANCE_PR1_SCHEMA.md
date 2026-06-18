# Enterprise Governance Foundation PR 1: Schema Preparation

This PR prepares enterprise governance schema only.

Included:

- Tenancy-ready columns and indexes for governed records.
- Identity and RBAC schema tables.
- Future audit hash-chain fields on `audit_events`.
- Regulation, control framework, control requirement, and governed-action mapping tables.
- Evidence graph foundation tables.
- Initial control framework seed definitions and an optional additive migration helper.

Not included:

- Tenant scoping enforcement.
- RBAC checks.
- Audit hash-chain generation or verification.
- Evidence packet export service.
- Runtime changes to the Gmail governed execution flow.
- UI, autonomous execution, or new connectors.

The schema supports evidence collection, control mapping, audit readiness, and governance workflows. It does not claim compliance certification.

Later PRs should add tenant enforcement, RBAC enforcement, audit hash-chain behavior, evidence export services, and operational hardening.
