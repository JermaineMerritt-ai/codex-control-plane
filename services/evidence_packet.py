"""Evidence packet generation + export (PR 7 — export only).

Assembles an exportable evidence packet from the evidence graph (PR 6), the
audit hash-chain verification (PR 2), the control catalog (PR 5), tenant
isolation (PR 3), and RBAC (PR 4). Packets are generated on demand (read-only);
nothing is persisted here and the execution pipeline is untouched.

An evidence packet **supports evidence collection, control mapping, audit
readiness, and governance workflows.** It does not certify, guarantee, or
represent a regulatory determination of compliance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.governance_seed import CONTROL_MAPPING_LANGUAGE
from services import evidence_graph
from services.audit_service import verify_chain, verify_tenant_events

DISCLAIMER = (
    "This packet supports evidence collection, control mapping, audit readiness, "
    "and governance workflows. It is provided for audit-readiness and governance "
    "review only and is not a certification, guarantee, or regulatory "
    "determination of compliance."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify(session: Session, tenant_id: str | None) -> dict[str, Any]:
    if tenant_id is not None:
        result = verify_tenant_events(session, tenant_id)
        scope = "tenant_self_hash"
    else:
        result = verify_chain(session)
        scope = "global_chain"
    return {
        "scope": scope,
        "status": result.status,
        "ok": result.ok,
        "verified_count": result.verified_count,
        "total_count": result.total_count,
        "reason": result.reason,
        "broken_at_seq": result.broken_at_seq,
    }


_APPROVAL_STATUS_MAP = {"pending": "pending_approval", "approved": "approved", "rejected": "rejected"}


def _effective_action_status(action: Any, approval: Any) -> str:
    """Effective governed-action status for display.

    The approval is the source of truth for the decision; the stored
    `action.status` is set at submit time and is not mutated on the (generic,
    Phase-1) approval transition. So when a governed action has a linked
    approval, render the action's status from that approval's final state.
    """
    if approval is not None:
        return _APPROVAL_STATUS_MAP.get(approval.status, action.status)
    return action.status


def _assemble(
    session: Session,
    *,
    packet_type: str,
    scope_id: str | None,
    tenant_id: str | None,
    graphs: list[dict[str, Any]],
    workflow: Any = None,
    time_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verification = _verify(session, tenant_id)

    governed_actions: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    policy_decisions: list[dict[str, Any]] = []
    execution_history: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []
    mapped_controls: list[dict[str, Any]] = []
    mapped_regulations: set[str] = set()
    evidence_artifacts: list[dict[str, Any]] = []
    gaps: set[str] = set()

    for graph in graphs:
        action = graph["governed_action"]
        governed_actions.append(
            {
                "id": action.id,
                "action_type": action.action_type,
                "status": _effective_action_status(action, graph["approval"]),
            }
        )

        if graph["approval"] is not None:
            approvals.append(
                {"governed_action_id": action.id, "id": graph["approval"].id, "status": graph["approval"].status}
            )
        else:
            gaps.add("missing_approval")

        policy_decisions.append(
            {
                "governed_action_id": action.id,
                "policy_version": graph["policy_decision"]["version"],
                "decision": graph["policy_decision"]["decision"],
            }
        )

        execution_history.append(
            {
                "governed_action_id": action.id,
                "source_job": (
                    {"id": graph["source_job"].id, "status": graph["source_job"].status}
                    if graph.get("source_job")
                    else None
                ),
                "execution_job": (
                    {"id": graph["execution_job"].id, "status": graph["execution_job"].status}
                    if graph.get("execution_job")
                    else None
                ),
            }
        )

        if graph["audit_events"]:
            for event in graph["audit_events"]:
                audit_events.append(
                    {
                        "id": event.id,
                        "seq": event.seq,
                        "action": event.action,
                        "resource_type": event.resource_type,
                        "resource_id": event.resource_id,
                    }
                )
        else:
            gaps.add("missing_audit_records")

        if graph["control_mappings"]:
            for mapping in graph["control_mappings"]:
                control = mapping["control"]
                framework = mapping["framework"]
                mapped_controls.append(
                    {
                        "governed_action_id": action.id,
                        "code": control.code if control else None,
                        "title": control.title if control else None,
                        "framework": framework.name if framework else None,
                    }
                )
                if mapping["regulation"] is not None:
                    mapped_regulations.add(mapping["regulation"].name)
        else:
            gaps.add("missing_control_mappings")

        if graph["evidence_artifacts"]:
            for artifact in graph["evidence_artifacts"]:
                evidence_artifacts.append(
                    {
                        "governed_action_id": action.id,
                        "id": artifact.id,
                        "artifact_type": artifact.artifact_type,
                        "uri": artifact.uri,
                    }
                )
        else:
            gaps.add("missing_evidence_artifacts")

    if verification["status"] == "failed":
        gaps.add("broken_audit_chain")

    workflow_ref = {"id": workflow.id, "name": workflow.name} if workflow is not None else None

    packet: dict[str, Any] = {
        "packet_type": packet_type,
        "scope_id": scope_id,
        "tenant_id": tenant_id,
        "generated_at": _now_iso(),
        "tenant": {"id": tenant_id},
        "workflow": workflow_ref,
        "time_range": time_range,
        "governed_actions": governed_actions,
        "approvals": approvals,
        "policy_decisions": policy_decisions,
        "execution_history": execution_history,
        "audit_events": audit_events,
        "audit_chain_verification": verification,
        "mapped_controls": mapped_controls,
        "mapped_regulations": sorted(mapped_regulations),
        "evidence_artifacts": evidence_artifacts,
        "evidence_gaps": sorted(gaps),
        "disclaimer": DISCLAIMER,
    }
    packet["executive_summary"] = _summary(packet)
    return packet


def _summary(packet: dict[str, Any]) -> str:
    n_actions = len(packet["governed_actions"])
    n_controls = len(packet["mapped_controls"])
    n_artifacts = len(packet["evidence_artifacts"])
    n_gaps = len(packet["evidence_gaps"])
    chain = packet["audit_chain_verification"]["status"]
    return (
        f"Evidence packet ({packet['packet_type']}) for tenant {packet['tenant_id']}: "
        f"{n_actions} governed action(s), {len(packet['approvals'])} approval(s), "
        f"{len(packet['audit_events'])} audit event(s), {n_controls} mapped control(s), "
        f"{n_artifacts} evidence artifact(s). Audit chain verification: {chain}. "
        f"{n_gaps} evidence gap(s) identified. "
        f"This packet {CONTROL_MAPPING_LANGUAGE}."
    )


# --- Packet builders -------------------------------------------------------

def build_action_packet(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    graph = evidence_graph.get_evidence_graph(
        session, governed_action_id=governed_action_id, tenant_id=tenant_id
    )
    if graph is None:
        return None
    return _assemble(
        session,
        packet_type="governed_action",
        scope_id=governed_action_id,
        tenant_id=tenant_id,
        graphs=[graph],
        workflow=graph["workflow"],
    )


def build_workflow_packet(
    session: Session, *, workflow_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    workflow = evidence_graph.get_workflow(session, workflow_id, tenant_id=tenant_id)
    if workflow is None:
        return None
    actions = evidence_graph.list_governed_actions(
        session, tenant_id=tenant_id, workflow_id=workflow_id
    )
    graphs = [
        g
        for g in (
            evidence_graph.get_evidence_graph(session, governed_action_id=a.id, tenant_id=tenant_id)
            for a in actions
        )
        if g is not None
    ]
    return _assemble(
        session,
        packet_type="workflow",
        scope_id=workflow_id,
        tenant_id=tenant_id,
        graphs=graphs,
        workflow=workflow,
    )


def build_tenant_packet(
    session: Session, *, tenant_id: str, start_at: Any = None, end_at: Any = None
) -> dict[str, Any]:
    actions = evidence_graph.list_governed_actions(
        session, tenant_id=tenant_id, start_at=start_at, end_at=end_at
    )
    graphs = [
        g
        for g in (
            evidence_graph.get_evidence_graph(session, governed_action_id=a.id, tenant_id=tenant_id)
            for a in actions
        )
        if g is not None
    ]
    time_range = None
    if start_at is not None or end_at is not None:
        time_range = {
            "start_at": start_at.isoformat() if hasattr(start_at, "isoformat") else start_at,
            "end_at": end_at.isoformat() if hasattr(end_at, "isoformat") else end_at,
        }
    return _assemble(
        session,
        packet_type="tenant",
        scope_id=tenant_id,
        tenant_id=tenant_id,
        graphs=graphs,
        time_range=time_range,
    )


# --- Export renderers ------------------------------------------------------

def render_json(packet: dict[str, Any]) -> str:
    return json.dumps(packet, indent=2, ensure_ascii=False, default=str)


def _md_list(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def render_markdown(packet: dict[str, Any]) -> str:
    v = packet["audit_chain_verification"]
    lines = [
        f"# Evidence Packet — {packet['packet_type']}",
        "",
        f"_Generated: {packet['generated_at']}_",
        "",
        "## Executive summary",
        packet["executive_summary"],
        "",
        f"**Tenant:** {packet['tenant_id']}",
        f"**Scope id:** {packet['scope_id']}",
    ]
    if packet.get("workflow"):
        lines.append(f"**Workflow:** {packet['workflow']['name']} (`{packet['workflow']['id']}`)")
    lines += [
        "",
        "## Audit chain verification",
        f"- scope: {v['scope']}",
        f"- status: **{v['status']}** (verified {v['verified_count']}/{v['total_count']})",
        f"- reason: {v['reason']}" if v["reason"] else "- reason: none",
        "",
        "## Governed actions",
        _md_list([f"{a['action_type']} — {a['status']} (`{a['id']}`)" for a in packet["governed_actions"]]),
        "",
        "## Approvals",
        _md_list([f"{a['status']} (`{a['id']}`)" for a in packet["approvals"]]),
        "",
        "## Policy decisions",
        _md_list([f"{p['decision']} (version {p['policy_version']})" for p in packet["policy_decisions"]]),
        "",
        "## Execution history",
        _md_list(
            [
                f"action {e['governed_action_id']}: source={e['source_job']} execution={e['execution_job']}"
                for e in packet["execution_history"]
            ]
        ),
        "",
        "## Audit events",
        _md_list([f"#{e['seq']} {e['action']} → {e['resource_type']}:{e['resource_id']}" for e in packet["audit_events"]]),
        "",
        "## Mapped controls",
        _md_list([f"{c['framework']} {c['code']} — {c['title']}" for c in packet["mapped_controls"]]),
        "",
        "## Mapped regulations",
        _md_list(packet["mapped_regulations"]),
        "",
        "## Evidence artifacts",
        _md_list([f"{a['artifact_type']} — {a['uri']}" for a in packet["evidence_artifacts"]]),
        "",
        "## Evidence gaps",
        _md_list(packet["evidence_gaps"]),
        "",
        "---",
        f"_{packet['disclaimer']}_",
    ]
    return "\n".join(lines)
