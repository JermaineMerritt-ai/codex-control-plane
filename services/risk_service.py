"""Deterministic risk classification for governance workflows (Phase 2).

Pure, rule-based scoring — no LLM, no external calls — so a given set of inputs
always yields the same risk level. Used by the AI Vendor / Automation Governance
Review workflow to decide whether human approval is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.policy_service import PolicyCategory

# Data sensitivity -> score. Unknown values fall back to a cautious 1.
_SENSITIVITY_SCORE: dict[str, int] = {
    "none": 0,
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "pii": 2,
    "phi": 3,
    "regulated": 3,
}

# Autonomy of the AI/automation -> score.
_AUTONOMY_SCORE: dict[str, int] = {
    "none": 0,
    "assisted": 1,
    "semi_autonomous": 2,
    "autonomous": 3,
}

# Policy category -> additional score.
_POLICY_SCORE: dict[PolicyCategory, int] = {
    PolicyCategory.read_only: 0,
    PolicyCategory.draft_only: 0,
    PolicyCategory.outbound_send: 1,
    PolicyCategory.publish: 1,
    PolicyCategory.destructive: 3,
}

HIGH_THRESHOLD = 6
MEDIUM_THRESHOLD = 3


@dataclass(frozen=True)
class RiskResult:
    level: str  # "low" | "medium" | "high"
    score: int
    reasons: list[str] = field(default_factory=list)


def _norm(value: str | None) -> str:
    return (value or "none").strip().lower()


def classify_risk(
    *,
    data_sensitivity: str | None,
    external_exposure: bool,
    autonomy_level: str | None,
    policy_category: PolicyCategory | None = None,
) -> RiskResult:
    """Classify governance risk as low/medium/high from deterministic signals."""
    score = 0
    reasons: list[str] = []

    sensitivity_key = _norm(data_sensitivity)
    sensitivity_points = _SENSITIVITY_SCORE.get(sensitivity_key, 1)
    score += sensitivity_points
    if sensitivity_points >= 2:
        reasons.append(f"sensitive data ({sensitivity_key})")

    if external_exposure:
        score += 2
        reasons.append("external exposure / outbound effect")

    autonomy_key = _norm(autonomy_level)
    autonomy_points = _AUTONOMY_SCORE.get(autonomy_key, 1)
    score += autonomy_points
    if autonomy_points >= 2:
        reasons.append(f"high autonomy ({autonomy_key})")

    if policy_category is not None:
        policy_points = _POLICY_SCORE.get(policy_category, 0)
        score += policy_points
        if policy_points >= 1:
            reasons.append(f"policy category {policy_category.value}")

    if score >= HIGH_THRESHOLD:
        level = "high"
    elif score >= MEDIUM_THRESHOLD:
        level = "medium"
    else:
        level = "low"

    if not reasons:
        reasons.append("no elevated risk signals")

    return RiskResult(level=level, score=score, reasons=reasons)
