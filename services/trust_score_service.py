"""Trust Score engine (PR 18, v0).

Generates an explainable 0-100 trust score for a governed action, workflow, or
tenant. Every score is derived from systems that already exist — the evidence
packet (which itself aggregates the governance graph, audit-chain verification,
approvals, control/regulation mappings, overrides, and evidence gaps), plus the
RBAC enforcement mode and tenant binding. There is no black-box scoring: the
returned breakdown lists, per dimension, the points earned out of the maximum and
the reason(s) why.

Trust scores support governance review and procurement validation. They are NOT a
certification, an attestation, or a guarantee of compliance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import TrustScore
from services import evidence_packet

# Score bands (inclusive lower bound).
BANDS: list[tuple[int, str]] = [
    (90, "Verified"),
    (75, "Strong"),
    (60, "Moderate"),
    (40, "Weak"),
    (0, "High Risk"),
]


def band_for(score: int) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "High Risk"


@dataclass
class Dimension:
    key: str
    label: str
    max_points: int
    earned: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.key,
            "label": self.label,
            "points": self.earned,
            "max_points": self.max_points,
            "reasons": self.reasons,
        }


# Each scorer receives the packet + app_env and mutates its Dimension.
# Max points sum to 100.
def _score_audit_integrity(d: Dimension, packet: dict, app_env: str) -> None:
    v = packet.get("audit_chain_verification", {})
    status = v.get("status")
    if status == "verified":
        d.earned = d.max_points
        d.reasons.append(f"audit chain verified ({v.get('verified_count')}/{v.get('total_count')})")
    elif status == "empty":
        d.reasons.append("no audit events recorded yet")
    else:
        d.reasons.append(f"audit chain not verified (status={status}, reason={v.get('reason')})")


def _score_approval_coverage(d: Dimension, packet: dict, app_env: str) -> None:
    approvals = packet.get("approvals", [])
    if not approvals:
        d.reasons.append("no approvals recorded for this scope")
        return
    statuses = [a.get("status") for a in approvals]
    approved = sum(1 for s in statuses if s == "approved")
    if approved == len(approvals):
        d.earned = d.max_points
        d.reasons.append(f"all {len(approvals)} approval(s) approved")
    elif approved:
        d.earned = round(d.max_points * approved / len(approvals))
        d.reasons.append(f"{approved}/{len(approvals)} approval(s) approved")
    else:
        d.reasons.append(f"{len(approvals)} approval(s) pending/rejected, none approved")


def _score_control_coverage(d: Dimension, packet: dict, app_env: str) -> None:
    controls = packet.get("mapped_controls", [])
    if controls:
        d.earned = d.max_points
        d.reasons.append(f"{len(controls)} control(s) mapped")
    else:
        d.reasons.append("no controls mapped (gap: missing_control_mappings)")


def _score_evidence_completeness(d: Dimension, packet: dict, app_env: str) -> None:
    gaps = packet.get("evidence_gaps", [])
    if not gaps:
        d.earned = d.max_points
        d.reasons.append("no evidence gaps identified")
    else:
        # Lose points proportionally to the number of distinct gaps (cap at max).
        penalty = min(d.max_points, len(gaps) * 4)
        d.earned = d.max_points - penalty
        d.reasons.append(f"{len(gaps)} evidence gap(s): {', '.join(gaps)}")


def _score_regulatory_mapping(d: Dimension, packet: dict, app_env: str) -> None:
    regs = packet.get("mapped_regulations", [])
    if regs:
        d.earned = d.max_points
        d.reasons.append(f"mapped to regulation(s): {', '.join(regs)}")
    else:
        d.reasons.append("no regulations mapped")


def _score_rbac_enforcement(d: Dimension, packet: dict, app_env: str) -> None:
    # Production/staging disable the demo operator/no-key bypass (PR 13).
    if app_env in ("production", "staging"):
        d.earned = d.max_points
        d.reasons.append(f"RBAC enforced (app_env={app_env}, no operator bypass)")
    else:
        d.earned = round(d.max_points / 2)
        d.reasons.append(f"demo mode (app_env={app_env}): operator bypass possible; harden for production")


def _score_tenant_isolation(d: Dimension, packet: dict, app_env: str) -> None:
    if packet.get("tenant_id"):
        d.earned = d.max_points
        d.reasons.append(f"scope bound to tenant {packet.get('tenant_id')}")
    else:
        d.reasons.append("scope is not tenant-bound (unscoped)")


def _score_incident_history(d: Dimension, packet: dict, app_env: str) -> None:
    overrides = packet.get("overrides", [])
    chain_failed = packet.get("audit_chain_verification", {}).get("status") == "failed"
    if chain_failed:
        d.reasons.append("audit chain failure is an open integrity incident")
        return
    if not overrides:
        d.earned = d.max_points
        d.reasons.append("no overrides or integrity incidents on record")
    else:
        # Documented overrides reduce clean-trust but are governed (not bypasses).
        d.earned = round(d.max_points / 2)
        d.reasons.append(f"{len(overrides)} documented human override(s) on record")


def _score_policy_enforcement(d: Dimension, packet: dict, app_env: str) -> None:
    decisions = packet.get("policy_decisions", [])
    bound = [pd for pd in decisions if pd.get("policy_version_id")]
    if decisions and len(bound) == len(decisions):
        d.earned = d.max_points
        d.reasons.append(f"all {len(decisions)} decision(s) bound to a policy version")
    elif bound:
        d.earned = round(d.max_points * len(bound) / len(decisions))
        d.reasons.append(f"{len(bound)}/{len(decisions)} decision(s) bound to a policy version")
    else:
        d.reasons.append("no policy version bound to the decision(s)")


def _score_execution_traceability(d: Dimension, packet: dict, app_env: str) -> None:
    actions = {e.get("action") for e in packet.get("audit_events", [])}
    has_submit = any(str(a).endswith("submitted") for a in actions)
    has_decision = any("approv" in str(a) for a in actions)
    earned = 0
    if has_submit:
        earned += d.max_points // 2
    if has_decision:
        earned += d.max_points - d.max_points // 2
    d.earned = earned
    if earned == d.max_points:
        d.reasons.append("lifecycle traceable end-to-end (submission through decision)")
    elif earned:
        d.reasons.append("lifecycle partially traceable")
    else:
        d.reasons.append("no traceable lifecycle events")


# (key, label, max_points, scorer) — max_points sum to 100.
_DIMENSIONS: list[tuple[str, str, int, Callable[[Dimension, dict, str], None]]] = [
    ("audit_integrity", "Audit Integrity", 15, _score_audit_integrity),
    ("approval_coverage", "Approval Coverage", 12, _score_approval_coverage),
    ("control_coverage", "Control Coverage", 12, _score_control_coverage),
    ("evidence_completeness", "Evidence Completeness", 12, _score_evidence_completeness),
    ("regulatory_mapping", "Regulatory Mapping Coverage", 10, _score_regulatory_mapping),
    ("rbac_enforcement", "RBAC Enforcement", 10, _score_rbac_enforcement),
    ("tenant_isolation", "Tenant Isolation Status", 8, _score_tenant_isolation),
    ("incident_history", "Incident History", 7, _score_incident_history),
    ("policy_enforcement", "Policy Enforcement", 7, _score_policy_enforcement),
    ("execution_traceability", "Execution Traceability", 7, _score_execution_traceability),
]

DISCLAIMER = (
    "Trust scores are derived from recorded governance evidence and support "
    "governance review and procurement validation. They are not a certification, "
    "attestation, or guarantee of compliance."
)


def score_packet(packet: dict[str, Any], *, app_env: str | None = None) -> dict[str, Any]:
    """Compute an explainable trust score from an evidence packet. Pure function."""
    env = app_env or get_settings().app_env
    dims = [Dimension(k, label, mx) for (k, label, mx, _scorer) in _DIMENSIONS]
    for dim, (_k, _l, _m, scorer) in zip(dims, _DIMENSIONS):
        scorer(dim, packet, env)
    total = sum(d.earned for d in dims)
    total = max(0, min(100, total))
    return {
        "score": total,
        "score_band": band_for(total),
        "max_score": 100,
        "breakdown": [d.to_dict() for d in dims],
        "disclaimer": DISCLAIMER,
    }


def _persist(
    session: Session, *, tenant_id: str | None, scope_type: str, scope_id: str, result: dict
) -> TrustScore:
    prior = (
        session.query(TrustScore)
        .filter(TrustScore.scope_type == scope_type, TrustScore.scope_id == scope_id)
    )
    if tenant_id is not None:
        prior = prior.filter(TrustScore.tenant_id == tenant_id)
    version = (max((p.version for p in prior.all()), default=0)) + 1
    row = TrustScore(
        tenant_id=tenant_id,
        scope_type=scope_type,
        scope_id=scope_id,
        score=result["score"],
        score_band=result["score_band"],
        score_breakdown=json.dumps(result["breakdown"]),
        version=version,
    )
    session.add(row)
    session.commit()
    return row


def _result_with_row(result: dict, row: TrustScore, scope_type: str, scope_id: str) -> dict:
    return {
        "score_id": row.id,
        "tenant_id": row.tenant_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "version": row.version,
        **result,
    }


def score_action(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None, persist: bool = True
) -> dict[str, Any] | None:
    packet = evidence_packet.build_action_packet(
        session, governed_action_id=governed_action_id, tenant_id=tenant_id
    )
    if packet is None:
        return None
    result = score_packet(packet)
    if not persist:
        return {"scope_type": "governed_action", "scope_id": governed_action_id, **result}
    row = _persist(session, tenant_id=tenant_id, scope_type="governed_action", scope_id=governed_action_id, result=result)
    return _result_with_row(result, row, "governed_action", governed_action_id)


def score_workflow(
    session: Session, *, workflow_id: str, tenant_id: str | None = None, persist: bool = True
) -> dict[str, Any] | None:
    packet = evidence_packet.build_workflow_packet(
        session, workflow_id=workflow_id, tenant_id=tenant_id
    )
    if packet is None:
        return None
    result = score_packet(packet)
    if not persist:
        return {"scope_type": "workflow", "scope_id": workflow_id, **result}
    row = _persist(session, tenant_id=tenant_id, scope_type="workflow", scope_id=workflow_id, result=result)
    return _result_with_row(result, row, "workflow", workflow_id)


def score_tenant(
    session: Session, *, tenant_id: str, persist: bool = True
) -> dict[str, Any]:
    packet = evidence_packet.build_tenant_packet(session, tenant_id=tenant_id)
    result = score_packet(packet)
    if not persist:
        return {"scope_type": "tenant", "scope_id": tenant_id, **result}
    row = _persist(session, tenant_id=tenant_id, scope_type="tenant", scope_id=tenant_id, result=result)
    return _result_with_row(result, row, "tenant", tenant_id)


def get_latest(
    session: Session, *, scope_type: str, scope_id: str, tenant_id: str | None = None
) -> TrustScore | None:
    q = (
        session.query(TrustScore)
        .filter(TrustScore.scope_type == scope_type, TrustScore.scope_id == scope_id)
    )
    if tenant_id is not None:
        q = q.filter(TrustScore.tenant_id == tenant_id)
    return q.order_by(TrustScore.version.desc()).first()
