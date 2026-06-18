"""Regulation + control mapping catalog (PR 5 — schema/seed only).

Seeds a representative reference catalog (frameworks, their top-level
controls/functions, a few regulations, sample requirements, and one industry
pack) and exposes read + mapping helpers. This is reference data plus
tenant-scoped action->control links — there is no evidence-graph logic here.

This capability **supports evidence collection, control mapping, audit
readiness, and governance workflows.** The seeded controls are the publicly
known top-level structures of each framework, not a complete control catalogue,
and nothing here guarantees, certifies, or claims compliance.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.governance_seed import CONTROL_MAPPING_LANGUAGE
from db.models import (
    Control,
    ControlFramework,
    ControlRequirement,
    GovernedActionControlMapping,
    IndustryControlPack,
    Regulation,
)

CATALOG_LANGUAGE = CONTROL_MAPPING_LANGUAGE
FRAMEWORK_VERSION = "current"

# Framework -> list of (code, title) for its real top-level functions /
# families / categories. Representative top level, not a full control set.
FRAMEWORK_CONTROLS: dict[str, list[tuple[str, str]]] = {
    "NIST AI RMF": [("GOVERN", "Govern"), ("MAP", "Map"), ("MEASURE", "Measure"), ("MANAGE", "Manage")],
    "NIST Cybersecurity Framework 2.0": [
        ("GV", "Govern"), ("ID", "Identify"), ("PR", "Protect"),
        ("DE", "Detect"), ("RS", "Respond"), ("RC", "Recover"),
    ],
    "ISO 27001": [
        ("A.5", "Organizational controls"), ("A.6", "People controls"),
        ("A.7", "Physical controls"), ("A.8", "Technological controls"),
    ],
    "ISO 42001": [
        ("CTX", "Context of the organization"), ("LEAD", "Leadership"),
        ("PLAN", "Planning"), ("SUP", "Support"), ("OPS", "Operation"),
        ("PERF", "Performance evaluation"), ("IMP", "Improvement"),
    ],
    "SOC 2": [
        ("CC", "Common Criteria (Security)"), ("A", "Availability"),
        ("PI", "Processing Integrity"), ("C", "Confidentiality"), ("P", "Privacy"),
    ],
    "HIPAA": [
        ("ADM", "Administrative Safeguards"), ("PHY", "Physical Safeguards"),
        ("TEC", "Technical Safeguards"), ("PRV", "Privacy Rule"),
        ("BRN", "Breach Notification Rule"),
    ],
    "GDPR": [
        ("ART5", "Principles (Art. 5)"), ("ART6", "Lawful basis (Art. 6)"),
        ("CH3", "Data subject rights (Ch. III)"), ("ART32", "Security of processing (Art. 32)"),
        ("ART33", "Breach notification (Art. 33-34)"),
    ],
    "EU AI Act": [
        ("CLASS", "Risk classification"), ("HIGHRISK", "High-risk requirements"),
        ("TRANSP", "Transparency obligations"), ("OVERSIGHT", "Human oversight"),
        ("PMM", "Post-market monitoring"),
    ],
    "NIST 800-53": [
        ("AC", "Access Control"), ("AU", "Audit and Accountability"),
        ("CA", "Assessment, Authorization, and Monitoring"), ("CM", "Configuration Management"),
        ("IR", "Incident Response"), ("RA", "Risk Assessment"),
        ("SC", "System and Communications Protection"), ("SI", "System and Information Integrity"),
    ],
    "NIST 800-171": [
        ("3.1", "Access Control"), ("3.3", "Audit and Accountability"),
        ("3.11", "Risk Assessment"), ("3.13", "System and Communications Protection"),
        ("3.14", "System and Information Integrity"),
    ],
    "CMMC": [
        ("L1", "Level 1 - Foundational"), ("L2", "Level 2 - Advanced"), ("L3", "Level 3 - Expert"),
    ],
    "SOX": [
        ("302", "Disclosure controls (Sec. 302)"), ("404", "Internal control over financial reporting (Sec. 404)"),
        ("409", "Real-time disclosure (Sec. 409)"),
    ],
    "FFIEC / model risk": [
        ("DEV", "Model development"), ("VAL", "Model validation"), ("GOV", "Governance and controls"),
    ],
    "DORA": [
        ("ICTRM", "ICT risk management"), ("INC", "ICT incident reporting"),
        ("TEST", "Digital operational resilience testing"), ("TPRM", "ICT third-party risk"),
        ("INFO", "Information sharing"),
    ],
}

# Regulatory instruments (the subset that are laws/regulations) + jurisdiction.
REGULATIONS: list[tuple[str, str]] = [
    ("HIPAA", "United States"),
    ("GDPR", "European Union"),
    ("EU AI Act", "European Union"),
    ("SOX", "United States"),
    ("DORA", "European Union"),
    ("FFIEC / model risk", "United States"),
]

# Representative requirements (framework_name, control_code, text, evidence_type).
SAMPLE_REQUIREMENTS: list[tuple[str, str, str, str]] = [
    ("NIST AI RMF", "GOVERN", "Establish and maintain AI governance policies, roles, and accountability.", "policy"),
    ("HIPAA", "TEC", "Implement technical access controls and audit logging for systems handling regulated data.", "audit_log"),
]


# --- Seeding ---------------------------------------------------------------

def _get_or_create_framework(session: Session, name: str) -> ControlFramework:
    fw = session.execute(
        select(ControlFramework).where(
            ControlFramework.name == name, ControlFramework.version == FRAMEWORK_VERSION
        )
    ).scalar_one_or_none()
    if fw is None:
        fw = ControlFramework(name=name, version=FRAMEWORK_VERSION, description=CATALOG_LANGUAGE)
        session.add(fw)
        session.flush()
    return fw


def _get_or_create_control(session: Session, framework_id: str, code: str, title: str) -> Control:
    ctrl = session.execute(
        select(Control).where(Control.framework_id == framework_id, Control.code == code)
    ).scalar_one_or_none()
    if ctrl is None:
        ctrl = Control(framework_id=framework_id, code=code, title=title, description=CATALOG_LANGUAGE)
        session.add(ctrl)
        session.flush()
    return ctrl


def seed_control_catalog(session: Session) -> None:
    """Idempotently seed the reference catalog. Safe to call at every startup."""
    controls_by_key: dict[tuple[str, str], Control] = {}
    for framework_name, controls in FRAMEWORK_CONTROLS.items():
        fw = _get_or_create_framework(session, framework_name)
        for code, title in controls:
            ctrl = _get_or_create_control(session, fw.id, code, title)
            controls_by_key[(framework_name, code)] = ctrl

    for name, jurisdiction in REGULATIONS:
        reg = session.execute(
            select(Regulation).where(Regulation.name == name)
        ).scalar_one_or_none()
        if reg is None:
            session.add(
                Regulation(name=name, jurisdiction=jurisdiction, description=CATALOG_LANGUAGE)
            )

    for framework_name, code, text, evidence_type in SAMPLE_REQUIREMENTS:
        ctrl = controls_by_key.get((framework_name, code))
        if ctrl is None:
            continue
        exists = session.execute(
            select(ControlRequirement).where(
                ControlRequirement.control_id == ctrl.id,
                ControlRequirement.requirement_text == text,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                ControlRequirement(
                    control_id=ctrl.id, requirement_text=text, evidence_type=evidence_type
                )
            )

    # One system-level industry pack (tenant-agnostic example).
    pack_name = "Healthcare AI Governance Starter"
    pack = session.execute(
        select(IndustryControlPack).where(
            IndustryControlPack.tenant_id.is_(None), IndustryControlPack.name == pack_name
        )
    ).scalar_one_or_none()
    if pack is None:
        hipaa_control_ids = [
            ctrl.id for (fw_name, _code), ctrl in controls_by_key.items() if fw_name == "HIPAA"
        ]
        session.add(
            IndustryControlPack(
                tenant_id=None,
                industry="Healthcare",
                name=pack_name,
                description=CATALOG_LANGUAGE,
                control_ids_json=json.dumps(hipaa_control_ids),
            )
        )

    session.commit()


# --- Read helpers (reference catalog) --------------------------------------

def list_frameworks(session: Session) -> list[ControlFramework]:
    return list(
        session.execute(select(ControlFramework).order_by(ControlFramework.name)).scalars().all()
    )


def get_framework(session: Session, framework_id: str) -> ControlFramework | None:
    return session.get(ControlFramework, framework_id)


def list_controls(session: Session, framework_id: str) -> list[Control]:
    return list(
        session.execute(
            select(Control).where(Control.framework_id == framework_id).order_by(Control.code)
        ).scalars().all()
    )


def get_control(session: Session, control_id: str) -> Control | None:
    return session.get(Control, control_id)


def list_regulations(session: Session) -> list[Regulation]:
    return list(
        session.execute(select(Regulation).order_by(Regulation.name)).scalars().all()
    )


# --- Governed-action <-> control mappings (tenant-scoped) ------------------

def create_action_control_mapping(
    session: Session,
    *,
    tenant_id: str | None,
    governed_action_id: str,
    control_id: str,
    regulation_id: str | None = None,
    rationale: str | None = None,
) -> GovernedActionControlMapping:
    """Link a governed action to a control. The unique constraint
    (tenant_id, governed_action_id, control_id) prevents duplicate links."""
    row = GovernedActionControlMapping(
        tenant_id=tenant_id,
        governed_action_id=governed_action_id,
        control_id=control_id,
        regulation_id=regulation_id,
        rationale=rationale,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_action_control_mappings(
    session: Session, *, governed_action_id: str, tenant_id: str | None = None
) -> list[GovernedActionControlMapping]:
    stmt = select(GovernedActionControlMapping).where(
        GovernedActionControlMapping.governed_action_id == governed_action_id
    )
    if tenant_id is not None:
        stmt = stmt.where(GovernedActionControlMapping.tenant_id == tenant_id)
    return list(session.execute(stmt).scalars().all())
