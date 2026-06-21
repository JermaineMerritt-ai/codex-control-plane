"""Incident replay (PR 17 — read-only reconstruction).

Reconstructs a governed action's full timeline and evidence context from what is
already recorded — reusing the evidence graph, audit-chain verification, and the
packet's gap detection. No writes, no schema, no execution, no UI.

`model_vendor_tool` is explicitly marked not_recorded/deferred: vendor/model
sovereignty metadata is a deferred Phase 3 item and is not invented here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from services import evidence_graph, evidence_packet

MODEL_VENDOR_TOOL_DEFERRED = {
    "status": "not_recorded",
    "note": "deferred (sovereignty controls); vendor/model metadata is not captured in this pilot",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_incident_replay(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """Assemble a read-only incident replay; None if missing/cross-tenant."""
    graph = evidence_graph.get_evidence_graph(
        session, governed_action_id=governed_action_id, tenant_id=tenant_id
    )
    if graph is None:
        return None
    # Reuse the packet for chain verification, gaps, approvals/overrides/artifacts.
    packet = evidence_packet.build_action_packet(
        session, governed_action_id=governed_action_id, tenant_id=tenant_id
    )

    action = graph["governed_action"]
    meta = json.loads(action.metadata_json) if action.metadata_json else {}
    intake = meta.get("intake", {})
    policy = meta.get("policy", {})
    risk = meta.get("risk", {})

    actor = None
    timeline: list[dict[str, Any]] = []
    for e in graph["audit_events"]:
        timeline.append(
            {
                "seq": e.seq,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "actor": e.actor,
                "at": e.created_at.isoformat() if e.created_at else None,
            }
        )
        if e.action == "governance_review.submitted" and actor is None:
            actor = e.actor
    timeline.sort(key=lambda x: x["seq"] if x["seq"] is not None else 0)

    effective_status = (
        packet["governed_actions"][0]["status"] if packet["governed_actions"] else action.status
    )

    return {
        "incident": {
            "governed_action_id": action.id,
            "action_type": action.action_type,
            "status": effective_status,
            "generated_at": _now_iso(),
        },
        "tenant": {"id": tenant_id},
        "original_request": intake,
        "actor": actor,
        "model_vendor_tool": MODEL_VENDOR_TOOL_DEFERRED,
        "policy": {
            "version": action.policy_version,
            "policy_version_id": action.policy_version_id,
            "decision": action.policy_decision,
            "category": policy.get("category"),
        },
        "risk": risk,
        "approvals": packet.get("approvals", []),
        "overrides": packet.get("overrides", []),
        "data_touched": {
            "data_sensitivity": intake.get("data_sensitivity"),
            "external_exposure": intake.get("external_exposure"),
            "autonomy_level": intake.get("autonomy_level"),
        },
        "outputs": {
            "evidence_artifacts": packet.get("evidence_artifacts", []),
            "execution_job": (
                {"id": graph["execution_job"].id, "status": graph["execution_job"].status}
                if graph.get("execution_job")
                else None
            ),
        },
        "audit_timeline": timeline,
        "audit_chain_verification": packet["audit_chain_verification"],
        "evidence_gaps": packet["evidence_gaps"],
        "disclaimer": evidence_packet.DISCLAIMER,
    }


def render_json(replay: dict[str, Any]) -> str:
    return json.dumps(replay, indent=2, ensure_ascii=False, default=str)


def _md_list(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def render_markdown(replay: dict[str, Any]) -> str:
    inc = replay["incident"]
    v = replay["audit_chain_verification"]
    return "\n".join(
        [
            f"# Incident Replay — {inc['action_type']}",
            "",
            f"_Generated: {inc['generated_at']}_",
            "",
            f"**Governed action:** `{inc['governed_action_id']}`  ·  **Status:** {inc['status']}",
            f"**Tenant:** {replay['tenant']['id']}  ·  **Actor:** {replay['actor']}",
            "",
            "## Original request",
            _md_list([f"{k}: {val}" for k, val in replay["original_request"].items()]),
            "",
            "## Model / vendor / tool",
            f"- {replay['model_vendor_tool']['status']} — {replay['model_vendor_tool']['note']}",
            "",
            "## Policy",
            f"- decision: {replay['policy']['decision']} · category: {replay['policy']['category']}",
            f"- version: {replay['policy']['version']} (`{replay['policy']['policy_version_id']}`)",
            "",
            "## Risk classification",
            f"- level: {replay['risk'].get('level')} · score: {replay['risk'].get('score')}",
            _md_list(replay["risk"].get("reasons", [])),
            "",
            "## Approvals",
            _md_list([f"{a['status']} (`{a['id']}`)" for a in replay["approvals"]]),
            "",
            "## Human overrides",
            _md_list(
                [
                    f"{o['accepted_risk']} risk accepted by {o['overridden_by_user_id']} — "
                    f"authority: {o['authority_basis']} (`{o['id']}`)"
                    for o in replay["overrides"]
                ]
            ),
            "",
            "## Data touched",
            _md_list([f"{k}: {val}" for k, val in replay["data_touched"].items()]),
            "",
            "## Outputs",
            _md_list([f"{a['artifact_type']} — {a['uri']}" for a in replay["outputs"]["evidence_artifacts"]]),
            f"- execution job: {replay['outputs']['execution_job']}",
            "",
            "## Audit timeline",
            _md_list([f"#{e['seq']} {e['action']} → {e['resource_type']}:{e['resource_id']} @ {e['at']}" for e in replay["audit_timeline"]]),
            "",
            "## Audit chain verification",
            f"- scope: {v['scope']} · status: **{v['status']}** (verified {v['verified_count']}/{v['total_count']})",
            "",
            "## Evidence gaps",
            _md_list(replay["evidence_gaps"]),
            "",
            "---",
            f"_{replay['disclaimer']}_",
        ]
    )
