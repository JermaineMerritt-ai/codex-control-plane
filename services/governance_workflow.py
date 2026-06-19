"""AI Vendor / Automation Governance Review workflow (Phase 2 pilot spine).

This is pure orchestration over existing Phase 1 services — it adds NO new
governance engine. The loop:

    intake -> policy evaluation -> risk classification -> governed action
      -> approval gate (if policy requires it OR risk is medium/high)
      -> audit events at each step -> evidence artifact (packet path reuses PR 7)

Tenant scoping and RBAC are enforced at the API layer; this module takes the
already-resolved tenant_id/actor.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from services import approval_service, audit_service, evidence_graph
from services.policy_service import PolicyCategory, evaluate_action
from services.risk_service import RiskResult, classify_risk

ACTION_TYPE = "ai_vendor.governance_review"
POLICY_VERSION = "pilot-v1"

# Workflow audit actions (kept local; recorded via the shared audit chain).
A_SUBMITTED = "governance_review.submitted"
A_POLICY = "governance_review.policy_evaluated"
A_RISK = "governance_review.risk_classified"
A_APPROVAL_REQUIRED = "governance_review.approval_required"
A_AUTO_CLEARED = "governance_review.auto_cleared"
A_BLOCKED = "governance_review.blocked"


def _policy_category_for(*, external_exposure: bool, autonomy_level: str | None) -> PolicyCategory:
    """Map intake signals to a policy bucket (conservative defaults)."""
    autonomy = (autonomy_level or "").strip().lower()
    if external_exposure or autonomy in ("autonomous", "semi_autonomous"):
        return PolicyCategory.outbound_send  # approval-gated by policy
    return PolicyCategory.draft_only


def _audit(session: Session, *, action: str, ga_id: str, tenant_id: str | None,
           actor: str | None, metadata: dict[str, Any]) -> None:
    audit_service.record(
        session,
        action=action,
        resource_type="governed_action",
        resource_id=ga_id,
        tenant_id=tenant_id,
        actor=actor,
        action_type=ACTION_TYPE,
        metadata=metadata,
    )


def submit_vendor_governance_review(
    session: Session,
    *,
    tenant_id: str | None,
    actor: str | None,
    vendor_name: str,
    system_type: str,
    intended_use: str,
    data_sensitivity: str | None = None,
    external_exposure: bool = False,
    autonomy_level: str | None = None,
) -> dict[str, Any]:
    """Run one governance review end to end and return a run summary."""
    intake = {
        "vendor_name": vendor_name,
        "system_type": system_type,
        "intended_use": intended_use,
        "data_sensitivity": data_sensitivity,
        "external_exposure": external_exposure,
        "autonomy_level": autonomy_level,
    }

    # 1) Policy evaluation (reused, unchanged).
    category = _policy_category_for(external_exposure=external_exposure, autonomy_level=autonomy_level)
    policy = evaluate_action(category)

    # 2) Risk classification (deterministic).
    risk: RiskResult = classify_risk(
        data_sensitivity=data_sensitivity,
        external_exposure=external_exposure,
        autonomy_level=autonomy_level,
        policy_category=category,
    )

    requires_approval = bool(policy.requires_approval or risk.level in ("medium", "high"))
    if policy.blocked:
        status = "blocked"
    elif requires_approval:
        status = "pending_approval"
    else:
        status = "cleared"

    # 3) Governed action record (the graph hub).
    action = evidence_graph.create_governed_action(
        session,
        tenant_id=tenant_id,
        action_type=ACTION_TYPE,
        policy_version=POLICY_VERSION,
        policy_decision=category.value,
        status=status,
        metadata={
            "intake": intake,
            "policy": {
                "category": category.value,
                "requires_approval": policy.requires_approval,
                "blocked": policy.blocked,
                "reason": policy.reason,
            },
            "risk": {"level": risk.level, "score": risk.score, "reasons": risk.reasons},
        },
    )

    # 4) Risk assessment record + audit trail.
    evidence_graph.create_risk_assessment(
        session,
        tenant_id=tenant_id,
        risk_level=risk.level,
        summary=f"{vendor_name}: {risk.level} risk (score {risk.score})",
        metadata={"reasons": risk.reasons, "governed_action_id": action.id},
    )
    _audit(session, action=A_SUBMITTED, ga_id=action.id, tenant_id=tenant_id, actor=actor,
           metadata={"vendor_name": vendor_name, "system_type": system_type})
    _audit(session, action=A_POLICY, ga_id=action.id, tenant_id=tenant_id, actor=actor,
           metadata={"category": category.value, "requires_approval": policy.requires_approval,
                     "blocked": policy.blocked})
    _audit(session, action=A_RISK, ga_id=action.id, tenant_id=tenant_id, actor=actor,
           metadata={"level": risk.level, "score": risk.score, "reasons": risk.reasons})

    # 5) Approval gate (reused approval service) when required.
    approval_id: str | None = None
    if policy.blocked:
        _audit(session, action=A_BLOCKED, ga_id=action.id, tenant_id=tenant_id, actor=actor,
               metadata={"reason": policy.reason})
    elif requires_approval:
        approval = approval_service.create_request(
            session,
            kind="governance.review",
            tenant_id=tenant_id,
            job_id=action.id,  # link the approval to the governed action
            payload={
                "workflow": ACTION_TYPE,
                "governed_action_id": action.id,
                "risk_level": risk.level,
                "policy_category": category.value,
            },
        )
        approval_id = approval.id
        action.approval_id = approval.id
        session.add(action)
        session.commit()
        _audit(session, action=A_APPROVAL_REQUIRED, ga_id=action.id, tenant_id=tenant_id, actor=actor,
               metadata={"approval_id": approval.id, "risk_level": risk.level})
    else:
        _audit(session, action=A_AUTO_CLEARED, ga_id=action.id, tenant_id=tenant_id, actor=actor,
               metadata={"risk_level": risk.level})

    # 6) Evidence artifact (packet path reuses the existing evidence service).
    evidence_graph.record_evidence_artifact(
        session,
        tenant_id=tenant_id,
        governed_action_id=action.id,
        artifact_type="governance_review_intake",
        metadata={"intake": intake, "risk_level": risk.level, "policy_category": category.value},
    )

    return {
        "governed_action_id": action.id,
        "action_type": ACTION_TYPE,
        "status": status,
        "requires_approval": requires_approval,
        "approval_id": approval_id,
        "policy": {
            "category": category.value,
            "requires_approval": policy.requires_approval,
            "blocked": policy.blocked,
            "reason": policy.reason,
        },
        "risk": {"level": risk.level, "score": risk.score, "reasons": risk.reasons},
    }


def _run_status(action: Any, approval: Any) -> str:
    meta = json.loads(action.metadata_json) if action.metadata_json else {}
    if meta.get("policy", {}).get("blocked"):
        return "blocked"
    if action.approval_id is None:
        return "cleared"
    if approval is None:
        return action.status
    return {
        "pending": "pending_approval",
        "approved": "approved",
        "rejected": "rejected",
    }.get(approval.status, approval.status)


def get_run(session: Session, *, governed_action_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Tenant-scoped run status, assembled from the existing evidence graph."""
    graph = evidence_graph.get_evidence_graph(
        session, governed_action_id=governed_action_id, tenant_id=tenant_id
    )
    if graph is None:
        return None
    action = graph["governed_action"]
    approval = graph["approval"]
    meta = json.loads(action.metadata_json) if action.metadata_json else {}

    # Workflow step events are keyed to the governed action; the evidence graph
    # gathers approval/job-keyed events. Union both for an accurate run count.
    action_events = audit_service.list_for_resource(
        session, resource_type="governed_action", resource_id=action.id, tenant_id=tenant_id
    )
    audit_event_ids = {e.id for e in action_events} | {e.id for e in graph["audit_events"]}

    return {
        "governed_action_id": action.id,
        "action_type": action.action_type,
        "status": _run_status(action, approval),
        "approval_id": action.approval_id,
        "approval_status": approval.status if approval else None,
        "policy": meta.get("policy"),
        "risk": meta.get("risk"),
        "intake": meta.get("intake"),
        "audit_event_count": len(audit_event_ids),
        "evidence_artifact_count": len(graph["evidence_artifacts"]),
    }


def list_runs(session: Session, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Tenant-scoped list of governance-review runs."""
    actions = evidence_graph.list_governed_actions(session, tenant_id=tenant_id)
    runs = []
    for action in actions:
        if action.action_type != ACTION_TYPE:
            continue
        meta = json.loads(action.metadata_json) if action.metadata_json else {}
        runs.append(
            {
                "governed_action_id": action.id,
                "status": action.status,
                "approval_id": action.approval_id,
                "risk": meta.get("risk"),
                "policy_decision": action.policy_decision,
            }
        )
    return runs
