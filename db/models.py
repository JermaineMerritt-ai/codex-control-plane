"""ORM models: system of record for jobs, approvals, tenancy, audit, and governance schema prep."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_TENANT_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_TENANT_NAME = "Default Development Tenant"


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), nullable=False, index=True)
    permission_id: Mapped[str] = mapped_column(String(36), ForeignKey("permissions.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GovernancePolicy(Base):
    __tablename__ = "governance_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version", name="uq_policy_tenant_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Policy versioning (PR 15): lifecycle + provenance. `id` is the policy_version_id.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.pending.value)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ApprovalStatus.pending.value)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tamper-evident hash chain (PR 2). `seq` orders the global chain; `event_hash`
    # commits to the immutable core fields plus `previous_hash`. Nullable so that
    # any pre-chain (legacy) rows remain valid and are skipped by verification.
    # UNIQUE so two concurrent writers cannot fork the chain at the same position:
    # the loser of the race hits an IntegrityError and retries (see audit_service).
    # NULLs are distinct in both SQLite and Postgres, so legacy NULL rows are fine.
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailThreadRecord(Base):
    """Durable Gmail (or virtual) thread pointer for operator workflows."""

    __tablename__ = "email_threads"
    __table_args__ = (UniqueConstraint("tenant_id", "external_thread_id", name="uq_email_thread_tenant_ext"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    external_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    last_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmailDeliveryRecord(Base):
    """Outbound email pipeline: draft -> approval -> send, with external ids."""

    __tablename__ = "email_deliveries"
    __table_args__ = (UniqueConstraint("approval_id", name="uq_email_delivery_approval"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    thread_external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gmail_draft_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("approval_requests.id"), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    execution_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft_created", index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlFramework(Base):
    __tablename__ = "control_frameworks"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_control_framework_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="current")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Control(Base):
    __tablename__ = "controls"
    __table_args__ = (UniqueConstraint("framework_id", "code", name="uq_control_framework_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    framework_id: Mapped[str] = mapped_column(String(36), ForeignKey("control_frameworks.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlRequirement(Base):
    __tablename__ = "control_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    control_id: Mapped[str] = mapped_column(String(36), ForeignKey("controls.id"), nullable=False, index=True)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndustryControlPack(Base):
    __tablename__ = "industry_control_packs"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_control_pack_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    industry: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiSystem(Base):
    __tablename__ = "ai_systems"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_ai_system_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_data_source_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_workflow_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    ai_system_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_systems.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernedAction(Base):
    __tablename__ = "governed_actions"
    __table_args__ = (UniqueConstraint("tenant_id", "source_job_id", name="uq_governed_action_tenant_job"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    approval_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id"), nullable=True, index=True
    )
    execution_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Immutable binding to the exact policy version in effect at decision time (PR 15).
    policy_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("governance_policies.id"), nullable=True, index=True
    )
    policy_decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    ai_system_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_systems.id"), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False, default="unassessed")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlMapping(Base):
    __tablename__ = "control_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    control_id: Mapped[str] = mapped_column(String(36), ForeignKey("controls.id"), nullable=False, index=True)
    regulation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("regulations.id"), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernedActionControlMapping(Base):
    __tablename__ = "governed_action_control_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "governed_action_id", "control_id", name="uq_action_control_tenant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    governed_action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("governed_actions.id"), nullable=False, index=True
    )
    control_id: Mapped[str] = mapped_column(String(36), ForeignKey("controls.id"), nullable=False, index=True)
    regulation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("regulations.id"), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    governed_action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("governed_actions.id"), nullable=True, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(128), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidencePacket(Base):
    __tablename__ = "evidence_packets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_export: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_export: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    # Persistence (PR 14): integrity hash, per-scope version, retention lifecycle.
    packet_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
