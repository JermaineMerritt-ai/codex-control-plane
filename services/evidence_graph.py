"""Evidence graph foundation (PR 6 — data/service foundation only).

Provides tenant-scoped creation and read helpers for the governance graph nodes
and a read-only assembler that walks the chain:

    AI System -> Workflow -> Governed Action -> Policy Decision -> Approval
      -> Execution -> Audit Event -> Control Mapping -> Regulation
      -> Evidence Artifact

`GovernedAction` is the hub: it carries the workflow, approval, execution-job,
and source-job links plus the policy decision, and is referenced by control
mappings and evidence artifacts.

This **supports evidence collection, control mapping, audit readiness, and
governance workflows.** It does not generate export packets (PR 7), change the
execution pipeline, or make any compliance claim.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    AiSystem,
    ApprovalRequest,
    AuditEvent,
    Control,
    ControlFramework,
    DataSource,
    EvidenceArtifact,
    GovernedAction,
    GovernedActionControlMapping,
    Job,
    Regulation,
    RiskAssessment,
    Workflow,
)


def _scoped(obj: Any, tenant_id: str | None) -> Any:
    """Return obj only if it belongs to tenant_id (or scoping is disabled)."""
    if obj is None:
        return None
    if tenant_id is not None and getattr(obj, "tenant_id", None) != tenant_id:
        return None
    return obj


# --- Node creation (tenant-scoped foundation) ------------------------------

def create_ai_system(
    session: Session, *, tenant_id: str | None, name: str,
    description: str | None = None, owner_user_id: str | None = None,
) -> AiSystem:
    row = AiSystem(tenant_id=tenant_id, name=name, description=description, owner_user_id=owner_user_id)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_data_source(
    session: Session, *, tenant_id: str | None, name: str, source_type: str,
    metadata: dict[str, Any] | None = None,
) -> DataSource:
    row = DataSource(
        tenant_id=tenant_id, name=name, source_type=source_type,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_workflow(
    session: Session, *, tenant_id: str | None, name: str,
    ai_system_id: str | None = None, description: str | None = None,
) -> Workflow:
    row = Workflow(tenant_id=tenant_id, name=name, ai_system_id=ai_system_id, description=description)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_governed_action(
    session: Session, *, tenant_id: str | None, action_type: str,
    workflow_id: str | None = None, source_job_id: str | None = None,
    approval_id: str | None = None, execution_job_id: str | None = None,
    policy_version: str | None = None, policy_decision: str | None = None,
    status: str = "pending", metadata: dict[str, Any] | None = None,
) -> GovernedAction:
    """Create a governed-action graph node. The link fields (source_job_id,
    approval_id, execution_job_id, workflow_id) connect existing execution
    concepts to the graph without changing the pipeline."""
    row = GovernedAction(
        tenant_id=tenant_id, action_type=action_type, workflow_id=workflow_id,
        source_job_id=source_job_id, approval_id=approval_id, execution_job_id=execution_job_id,
        policy_version=policy_version, policy_decision=policy_decision, status=status,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_risk_assessment(
    session: Session, *, tenant_id: str | None, risk_level: str,
    ai_system_id: str | None = None, workflow_id: str | None = None,
    summary: str | None = None, metadata: dict[str, Any] | None = None,
) -> RiskAssessment:
    row = RiskAssessment(
        tenant_id=tenant_id, ai_system_id=ai_system_id, workflow_id=workflow_id,
        risk_level=risk_level, summary=summary,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def record_evidence_artifact(
    session: Session, *, tenant_id: str | None, artifact_type: str,
    governed_action_id: str | None = None, uri: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvidenceArtifact:
    row = EvidenceArtifact(
        tenant_id=tenant_id, governed_action_id=governed_action_id, artifact_type=artifact_type,
        uri=uri, metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# --- Reads (tenant-scoped) -------------------------------------------------

def list_ai_systems(session: Session, *, tenant_id: str | None = None) -> list[AiSystem]:
    stmt = select(AiSystem).order_by(AiSystem.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(AiSystem.tenant_id == tenant_id)
    return list(session.execute(stmt).scalars().all())


def get_ai_system(session: Session, ai_system_id: str, *, tenant_id: str | None = None) -> AiSystem | None:
    return _scoped(session.get(AiSystem, ai_system_id), tenant_id)


def list_workflows(
    session: Session, *, tenant_id: str | None = None, ai_system_id: str | None = None
) -> list[Workflow]:
    stmt = select(Workflow).order_by(Workflow.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(Workflow.tenant_id == tenant_id)
    if ai_system_id is not None:
        stmt = stmt.where(Workflow.ai_system_id == ai_system_id)
    return list(session.execute(stmt).scalars().all())


def get_workflow(session: Session, workflow_id: str, *, tenant_id: str | None = None) -> Workflow | None:
    return _scoped(session.get(Workflow, workflow_id), tenant_id)


def get_governed_action(
    session: Session, governed_action_id: str, *, tenant_id: str | None = None
) -> GovernedAction | None:
    return _scoped(session.get(GovernedAction, governed_action_id), tenant_id)


def list_governed_actions(
    session: Session,
    *,
    tenant_id: str | None = None,
    workflow_id: str | None = None,
    start_at: Any = None,
    end_at: Any = None,
) -> list[GovernedAction]:
    stmt = select(GovernedAction).order_by(GovernedAction.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(GovernedAction.tenant_id == tenant_id)
    if workflow_id is not None:
        stmt = stmt.where(GovernedAction.workflow_id == workflow_id)
    if start_at is not None:
        stmt = stmt.where(GovernedAction.created_at >= start_at)
    if end_at is not None:
        stmt = stmt.where(GovernedAction.created_at <= end_at)
    return list(session.execute(stmt).scalars().all())


def list_evidence_artifacts(
    session: Session, *, tenant_id: str | None = None, governed_action_id: str | None = None
) -> list[EvidenceArtifact]:
    stmt = select(EvidenceArtifact).order_by(EvidenceArtifact.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(EvidenceArtifact.tenant_id == tenant_id)
    if governed_action_id is not None:
        stmt = stmt.where(EvidenceArtifact.governed_action_id == governed_action_id)
    return list(session.execute(stmt).scalars().all())


# --- Graph assembly (read-only; NOT an export packet) ----------------------

def get_evidence_graph(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """Assemble the connected graph for one governed action, tenant-scoped.
    Returns None if the action does not exist or belongs to another tenant.
    This is a read assembly only — it does not persist or export anything."""
    action = get_governed_action(session, governed_action_id, tenant_id=tenant_id)
    if action is None:
        return None

    workflow = _scoped(session.get(Workflow, action.workflow_id), tenant_id) if action.workflow_id else None
    ai_system = (
        _scoped(session.get(AiSystem, workflow.ai_system_id), tenant_id)
        if workflow and workflow.ai_system_id
        else None
    )
    approval = _scoped(session.get(ApprovalRequest, action.approval_id), tenant_id) if action.approval_id else None
    source_job = _scoped(session.get(Job, action.source_job_id), tenant_id) if action.source_job_id else None
    execution_job = (
        _scoped(session.get(Job, action.execution_job_id), tenant_id) if action.execution_job_id else None
    )

    # Include the governed action's own id so workflow step events (recorded with
    # resource_type="governed_action") surface in the graph/evidence packet, not
    # only the approval/job-keyed events.
    resource_ids = [
        rid
        for rid in (action.id, action.approval_id, action.source_job_id, action.execution_job_id)
        if rid
    ]
    audit_events: list[AuditEvent] = []
    if resource_ids:
        a_stmt = select(AuditEvent).where(AuditEvent.resource_id.in_(resource_ids)).order_by(AuditEvent.seq)
        if tenant_id is not None:
            a_stmt = a_stmt.where(AuditEvent.tenant_id == tenant_id)
        audit_events = list(session.execute(a_stmt).scalars().all())

    cm_stmt = select(GovernedActionControlMapping).where(
        GovernedActionControlMapping.governed_action_id == action.id
    )
    if tenant_id is not None:
        cm_stmt = cm_stmt.where(GovernedActionControlMapping.tenant_id == tenant_id)
    control_mappings: list[dict[str, Any]] = []
    for mapping in session.execute(cm_stmt).scalars().all():
        control = session.get(Control, mapping.control_id)
        framework = session.get(ControlFramework, control.framework_id) if control else None
        regulation = session.get(Regulation, mapping.regulation_id) if mapping.regulation_id else None
        control_mappings.append(
            {"control": control, "framework": framework, "regulation": regulation, "rationale": mapping.rationale}
        )

    artifacts = list_evidence_artifacts(session, tenant_id=tenant_id, governed_action_id=action.id)

    return {
        "governed_action": action,
        "ai_system": ai_system,
        "workflow": workflow,
        "policy_decision": {"version": action.policy_version, "decision": action.policy_decision},
        "approval": approval,
        "source_job": source_job,
        "execution_job": execution_job,
        "audit_events": audit_events,
        "control_mappings": control_mappings,
        "evidence_artifacts": artifacts,
    }
