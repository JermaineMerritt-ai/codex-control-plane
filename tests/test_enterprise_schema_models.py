from sqlalchemy import create_engine, inspect, select

from db import models
from db.governance_seed import (
    CONTROL_MAPPING_LANGUAGE,
    INITIAL_CONTROL_FRAMEWORK_NAMES,
    PERMISSION_NAMES,
    ROLE_NAMES,
)
from db.migration_scripts.m001_enterprise_governance_schema import upgrade


def test_enterprise_schema_tables_can_be_created():
    engine = create_engine("sqlite:///:memory:", future=True)
    models.Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())

    assert {
        "tenants",
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "api_keys",
        "regulations",
        "control_frameworks",
        "controls",
        "control_requirements",
        "industry_control_packs",
        "governed_action_control_mappings",
        "ai_systems",
        "data_sources",
        "workflows",
        "governed_actions",
        "risk_assessments",
        "control_mappings",
        "evidence_artifacts",
        "evidence_packets",
    }.issubset(tables)


def test_role_and_permission_constants_exist():
    assert ROLE_NAMES == (
        "Owner",
        "Admin",
        "Compliance Officer",
        "Auditor",
        "Operator",
        "Viewer",
    )
    assert set(PERMISSION_NAMES) == {
        "create_governed_action",
        "approve_action",
        "reject_action",
        "execute_approved_action",
        "view_audit",
        "export_evidence",
        "manage_policies",
        "manage_controls",
        "manage_users",
    }


def test_audit_event_hash_schema_fields_exist_without_behavior():
    columns = {column.name for column in models.AuditEvent.__table__.columns}
    assert {
        "actor_user_id",
        "actor_type",
        "action_type",
        "policy_version",
        "decision",
        "reason",
        "metadata_json",
        "previous_hash",
        "event_hash",
    }.issubset(columns)
    assert models.AuditEvent.__table__.columns["event_hash"].nullable is True


def test_control_framework_seed_definitions_exist():
    assert INITIAL_CONTROL_FRAMEWORK_NAMES == (
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
    assert CONTROL_MAPPING_LANGUAGE == (
        "supports evidence collection, control mapping, audit readiness, and governance workflows"
    )


def test_evidence_graph_models_import_successfully():
    assert models.AiSystem.__tablename__ == "ai_systems"
    assert models.DataSource.__tablename__ == "data_sources"
    assert models.Workflow.__tablename__ == "workflows"
    assert models.GovernedAction.__tablename__ == "governed_actions"
    assert models.RiskAssessment.__tablename__ == "risk_assessments"
    assert models.ControlMapping.__tablename__ == "control_mappings"
    assert models.EvidenceArtifact.__tablename__ == "evidence_artifacts"
    assert models.EvidencePacket.__tablename__ == "evidence_packets"


def test_optional_migration_helper_seeds_framework_names_only():
    engine = create_engine("sqlite:///:memory:", future=True)
    upgrade(engine)
    with engine.connect() as conn:
        names = set(conn.execute(select(models.ControlFramework.name)).scalars().all())
    assert set(INITIAL_CONTROL_FRAMEWORK_NAMES).issubset(names)
