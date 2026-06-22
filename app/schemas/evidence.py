"""Read schemas for the evidence graph (PR 6). Read-only views; no export."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StoredPacketResponse(BaseModel):
    id: str
    tenant_id: str | None = None
    scope_type: str
    scope_id: str | None = None
    version: int | None = None
    packet_hash: str | None = None
    retention_status: str
    created_by_user_id: str | None = None
    created_at: datetime
    # Signing (PR 20)
    signature_algorithm: str | None = None
    signed_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class StoredPacketListResponse(BaseModel):
    items: list[StoredPacketResponse] = Field(default_factory=list)


class RevokePacketRequest(BaseModel):
    reason: str


def stored_packet_to_response(row: Any) -> StoredPacketResponse:
    return StoredPacketResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        version=row.version,
        packet_hash=row.packet_hash,
        retention_status=row.retention_status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        signature_algorithm=getattr(row, "signature_algorithm", None),
        signed_at=getattr(row, "signed_at", None),
        expires_at=getattr(row, "expires_at", None),
        revoked_at=getattr(row, "revoked_at", None),
    )


class GraphRef(BaseModel):
    id: str
    label: str


class AuditEventNode(BaseModel):
    id: str
    seq: int | None = None
    action: str
    resource_type: str
    resource_id: str


class ControlMappingNode(BaseModel):
    control_id: str | None = None
    code: str | None = None
    title: str | None = None
    framework: str | None = None
    regulation: str | None = None
    rationale: str | None = None


class EvidenceArtifactNode(BaseModel):
    id: str
    artifact_type: str
    uri: str | None = None


class EvidenceGraphResponse(BaseModel):
    governed_action_id: str
    action_type: str
    status: str
    policy_version: str | None = None
    policy_decision: str | None = None
    ai_system: GraphRef | None = None
    workflow: GraphRef | None = None
    approval: GraphRef | None = None
    source_job_id: str | None = None
    execution_job_id: str | None = None
    audit_events: list[AuditEventNode] = Field(default_factory=list)
    control_mappings: list[ControlMappingNode] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifactNode] = Field(default_factory=list)


class GovernedActionSummary(BaseModel):
    id: str
    action_type: str
    status: str
    workflow_id: str | None = None
    approval_id: str | None = None
    execution_job_id: str | None = None


class GovernedActionListResponse(BaseModel):
    items: list[GovernedActionSummary] = Field(default_factory=list)


class AiSystemSummary(BaseModel):
    id: str
    name: str
    description: str | None = None


class AiSystemListResponse(BaseModel):
    items: list[AiSystemSummary] = Field(default_factory=list)


def governed_action_to_summary(row: Any) -> GovernedActionSummary:
    return GovernedActionSummary(
        id=row.id,
        action_type=row.action_type,
        status=row.status,
        workflow_id=row.workflow_id,
        approval_id=row.approval_id,
        execution_job_id=row.execution_job_id,
    )


def ai_system_to_summary(row: Any) -> AiSystemSummary:
    return AiSystemSummary(id=row.id, name=row.name, description=row.description)


def graph_to_response(graph: dict[str, Any]) -> EvidenceGraphResponse:
    action = graph["governed_action"]
    ai_system = graph.get("ai_system")
    workflow = graph.get("workflow")
    approval = graph.get("approval")
    return EvidenceGraphResponse(
        governed_action_id=action.id,
        action_type=action.action_type,
        status=action.status,
        policy_version=graph["policy_decision"]["version"],
        policy_decision=graph["policy_decision"]["decision"],
        ai_system=GraphRef(id=ai_system.id, label=ai_system.name) if ai_system else None,
        workflow=GraphRef(id=workflow.id, label=workflow.name) if workflow else None,
        approval=GraphRef(id=approval.id, label=approval.status) if approval else None,
        source_job_id=graph["source_job"].id if graph.get("source_job") else None,
        execution_job_id=graph["execution_job"].id if graph.get("execution_job") else None,
        audit_events=[
            AuditEventNode(
                id=e.id, seq=e.seq, action=e.action,
                resource_type=e.resource_type, resource_id=e.resource_id,
            )
            for e in graph["audit_events"]
        ],
        control_mappings=[
            ControlMappingNode(
                control_id=m["control"].id if m["control"] else None,
                code=m["control"].code if m["control"] else None,
                title=m["control"].title if m["control"] else None,
                framework=m["framework"].name if m["framework"] else None,
                regulation=m["regulation"].name if m["regulation"] else None,
                rationale=m["rationale"],
            )
            for m in graph["control_mappings"]
        ],
        evidence_artifacts=[
            EvidenceArtifactNode(id=a.id, artifact_type=a.artifact_type, uri=a.uri)
            for a in graph["evidence_artifacts"]
        ],
    )
