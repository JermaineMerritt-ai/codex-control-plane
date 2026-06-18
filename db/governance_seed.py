"""Enterprise governance schema seed definitions.

These constants prepare PR 1 schema and tests only. Runtime enforcement and
permission checks are intentionally left to later PRs.
"""

from __future__ import annotations

from db.models import DEFAULT_TENANT_ID, DEFAULT_TENANT_NAME

ROLE_NAMES: tuple[str, ...] = (
    "Owner",
    "Admin",
    "Compliance Officer",
    "Auditor",
    "Operator",
    "Viewer",
)

PERMISSION_NAMES: tuple[str, ...] = (
    "create_governed_action",
    "approve_action",
    "reject_action",
    "execute_approved_action",
    "view_audit",
    "export_evidence",
    "manage_policies",
    "manage_controls",
    "manage_users",
)

INITIAL_CONTROL_FRAMEWORK_NAMES: tuple[str, ...] = (
    "NIST AI RMF",
    "NIST Cybersecurity Framework 2.0",
    "ISO 27001",
    "ISO 42001",
    "SOC 2",
    "HIPAA",
    "GDPR",
    "EU AI Act",
    "NIST 800-53",
    "NIST 800-171",
    "CMMC",
    "SOX",
    "FFIEC / model risk",
    "DORA",
)

CONTROL_MAPPING_LANGUAGE = (
    "supports evidence collection, control mapping, audit readiness, and governance workflows"
)

__all__ = [
    "CONTROL_MAPPING_LANGUAGE",
    "DEFAULT_TENANT_ID",
    "DEFAULT_TENANT_NAME",
    "INITIAL_CONTROL_FRAMEWORK_NAMES",
    "PERMISSION_NAMES",
    "ROLE_NAMES",
]
