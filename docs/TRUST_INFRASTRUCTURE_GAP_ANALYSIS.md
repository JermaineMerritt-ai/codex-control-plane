# Trust Infrastructure — Gap Analysis & Implementation Plan (Phase 1)

**Status:** Phase 1 (FOUNDATIONAL / BLOCKING) — complete. No implementation code written.
**Mission:** evolve CodexDominion from an AI Governance Control Plane into AI Trust
Infrastructure (Trust Scores, Procurement Verification, Certification, Risk/Insurance
readiness, Trust Registry) by **extending existing architecture**, not rebuilding it.
All downstream phases (2–9) must reference this document.

> **Language guardrail (enforced):** "supports evidence collection / audit readiness /
> governance workflows" and "provides verifiable evidence." Never "guarantees /
> certifies compliance," "certified compliant," or "regulatory authorization."

---

## 0. Two decisions that gate everything below

**0.1 — The biggest risk in the source prompt is duplication.** The prompt instructs
creating a `models/` package (`models/trust_score.py`, `models/evidence_packet_record.py`,
`models/trust_verification.py`, `models/trust_registry.py`). **This repo has no `models/`
package** — all ORM models live in a single declarative module, [`db/models.py`](../db/models.py),
registered on one `Base.metadata`. New models MUST be added to `db/models.py` (or a `db/`
submodule imported into the same `Base`), or `init_db()`/`create_all` and the additive
migration scripts will never see them. A separate `models/` directory would silently
produce tables that don't exist at runtime. **Decision: extend `db/models.py`.**

Likewise, `models/evidence_packet_record.py` would **duplicate the existing
`EvidencePacket` model** (which already persists `packet_hash`, `version`,
`retention_status`). Phase 3 must **extend `EvidencePacket`**, not create a parallel table.

**0.2 — Sequencing vs. the feature freeze.** Feature development was frozen pending
pilot feedback, and there are currently **zero signed pilots**. Per the owner's own
modification: build **Trust Score (P2) → Signed/Verifiable Evidence (P3) → Procurement
Verification (P4)** first; **defer Trust Registry (P5) and Insurance Readiness (P6)**
until 2–3 pilot customers exist. This document plans all phases but recommends
implementing only P2→P3→P4 (plus the minimum of P8 that P3 needs), and **holding at a
review gate before each.** P2–P4 are defensible as *pilot-enabling* (they answer the
procurement questions surfaced in `../../CodexDominion_5.0_Pilot/MOCK_PROCUREMENT_REVIEW.md`);
P5/P6 are speculative without real customer data.

---

## 1. Repository assessment (the 10 required areas)

Legend: ✅ exists & reusable · 🟡 partial / extend · ❌ must build.

### 1.1 Audit chain architecture — ✅
[`services/audit_service.py`](../services/audit_service.py). Linked SHA-256 hash chain;
each event binds its immutable core fields + `previous_hash` (`GENESIS_HASH` root),
ordered by UNIQUE `seq` with retry-on-collision. Single write path `record()`.
Verification: global `verify_chain` + per-tenant `tenant_self_hash`. Model
[`AuditEvent`](../db/models.py) (models.py:163) stores `event_hash`, `previous_hash`, `seq`.
**Reuse as:** the *Audit Integrity* and *Execution Traceability* scoring inputs (P2),
the tamper check behind evidence verification (P3).
**Limit (tech debt):** the chain is **global**, not per-tenant; per-tenant integrity is a
self-hash recomputation, not an independent chain. Fine for pilot; a scale constraint for
multi-tenant trust claims (see §6).

### 1.2 Evidence packet architecture — ✅ (persistence already shipped)
[`services/evidence_packet.py`](../services/evidence_packet.py) builds action/workflow/tenant
packets, renders JSON + Markdown, honest `evidence_gaps`, `_effective_action_status`,
`DISCLAIMER`. [`services/evidence_store.py`](../services/evidence_store.py) **persists**
packets: `compute_packet_hash` (SHA-256 over canonical JSON), per-scope `version`,
supersede-prior, `retention_status`, and an `evidence.packet.generated` /
`evidence.packet.downloaded` audit trail. Model [`EvidencePacket`](../db/models.py:406)
already has `packet_hash`, `version`, `retention_status`, `json_export`, `markdown_export`.
**This is ~70% of the prompt's Phase 3.** Reuse for *Evidence Completeness* scoring (P2).

### 1.3 Governance graph architecture — ✅
[`services/evidence_graph.py`](../services/evidence_graph.py) `get_evidence_graph()` returns
the full chain: AiSystem → Workflow → GovernedAction → PolicyDecision → Approval →
source/execution Job → AuditEvents → ControlMappings → Regulations → EvidenceArtifacts →
Overrides. **Reuse as the single read model for every Trust Score dimension** — the scorer
should consume this graph, not re-query primitives.

### 1.4 Regulation / framework mappings — 🟡
[`services/control_catalog.py`](../services/control_catalog.py) seeds 11 frameworks:
NIST AI RMF, NIST CSF 2.0, SOC 2, HIPAA, GDPR, EU AI Act, NIST 800-53, NIST 800-171,
CMMC, SOX, **FFIEC / model risk**, DORA; plus `Regulation`s and `IndustryControlPack`s.
Action↔control links via [`GovernedActionControlMapping`](../db/models.py:375).
**Gap for Phase 7:** **ISO 42001 is NOT in the catalog** (the prompt lists it). Add it as a
framework + representative controls. Otherwise reuse wholesale for *Control / Regulatory
Coverage* scoring (P2) and the Compliance Translation engine (P7).

### 1.5 Approval workflows — ✅
[`services/approval_service.py`](../services/approval_service.py) +
[`services/governance_workflow.py`](../services/governance_workflow.py): intake → policy
eval → deterministic risk → approval gate (policy-required OR risk medium/high) → audit →
packet. [`services/override_service.py`](../services/override_service.py): human override
(`override_recorded`, not executed). **Reuse for *Approval Coverage* + *Policy Enforcement*
scoring (P2).** Note: Procurement Verification (P4) is a **distinct** lifecycle (verify a
*system/tenant*, not an *action*) — model it separately, do not overload `ApprovalRequest`.

### 1.6 Tenant isolation — ✅
Credential-bound tenancy ([`tenant_service.py`](../services/tenant_service.py),
`X-Api-Key` → `hash_api_key`), service-layer `tenant_id` filtering, cross-tenant → None/404.
Verified by [`test_tenant_isolation.py`](../tests/test_tenant_isolation.py). **Reuse as the
*Tenant Isolation Status* scoring input (P2)** and the access boundary for the registry (P5).

### 1.7 RBAC architecture — ✅ (production-hardened)
[`services/rbac_service.py`](../services/rbac_service.py): `Principal`, `ROLE_PERMISSIONS`
(Owner/Admin/Compliance Officer/Auditor/Operator/Reviewer/Viewer), `require_permission`.
**Production RBAC already done** ([`app/config.py`](../app/config.py) `app_env`
demo|staging|production; operator/no-key bypass only in demo) — verified by
[`test_production_rbac.py`](../tests/test_production_rbac.py). **This closes several Phase 8
items already.** Reuse for *RBAC Enforcement* scoring (P2); add new permissions for trust
ops (e.g. `manage_verification`, `publish_registry`).

### 1.8 API surfaces — ✅
[`app/main.py`](../app/main.py) registers routers: jobs, approvals, audit, controls, email,
evidence, workflows, policies, incidents; serves `/console`; seeds rbac+catalog+default
policy at startup. **New trust APIs follow this pattern:** add `app/api/trust.py`,
`app/api/verification.py`, `app/api/compliance.py`; register in `main.py`; gate with
`require_permission`; tenant-scope via `principal`.

### 1.9 Database schema — 🟡 (additive, no Alembic)
Single `Base` in [`db/models.py`](../db/models.py) (~30 models incl. `RiskAssessment`,
`ControlMapping`, `IndustryControlPack`, `EvidencePacket`, `ActionOverride`).
Migrations are **additive scripts** `db/migration_scripts/m001..m005` (`create_all` +
SQLite `ALTER TABLE ADD COLUMN`); **no Alembic, no down-migrations, SQLite-first** (Postgres
not CI-tested). New work continues the `m00N` pattern (m006+). **Tech debt — see §6.**
Note `RiskAssessment` (models.py:349) **exists but is under-used** — deterministic risk
currently lives in `GovernedAction` metadata via [`risk_service.py`](../services/risk_service.py);
P6 should reconcile (reuse the table or document why not), not add a third risk store.

### 1.10 Export mechanisms — ✅
Evidence packets export JSON + Markdown (`render_json`/`render_markdown`), persisted
exports stored on `EvidencePacket.json_export/markdown_export`, downloads audited
([`evidence.py`](../app/api/evidence.py)). Incident replay exports JSON + MD
([`incident_replay.py`](../services/incident_replay.py)). One-pager/packets → PDF via Chrome
headless (buyer folder). **Reuse for all P4/P6/P7/P9 report outputs** (JSON + MD, optional PDF).

---

## 2. Reuse-vs-build matrix (per proposed phase)

| Phase | Prompt says create | Reality | Action |
|---|---|---|---|
| P2 Trust Score | `services/trust_score_service.py`, `models/trust_score.py`, `/trust/*` | New (inputs all exist) | **BUILD** — new service + `TrustScore` model in `db/models.py` + `app/api/trust.py`. Consume `evidence_graph`. |
| P3 Signed Evidence | `models/evidence_packet_record.py`, `services/evidence_signature_service.py`, `/evidence/verify/{id}` | Persistence+hash+version+retention **already exist** (`EvidencePacket`, `evidence_store`) | **EXTEND** `EvidencePacket` (+`packet_signature`, `expires_at`, `revoked`/`verification_status`). Add signature service + `GET /evidence/verify/{id}`. **Do not** create `evidence_packet_record`. |
| P4 Procurement Verification | `models/trust_verification.py`, `/verification/*` | New lifecycle, distinct from approvals | **BUILD** new `TrustVerification` model + service + router. Reuse Trust Score (P2) + verified evidence (P3) as inputs. |
| P5 Trust Registry | `models/trust_registry.py`, `/registry/*` | New | **DEFER** until 2–3 pilots (owner directive). Plan only. |
| P6 Insurance Readiness | `services/risk_assessment_service.py`, `/risk/report/{tenant}` | `RiskAssessment` model + `risk_service` exist (per-action) | **DEFER** aggregate engine; when built, **reuse `RiskAssessment`** + scoring, don't rebuild risk primitives. |
| P7 Compliance Translation | `services/compliance_translation_service.py`, `/compliance/*` | Catalog exists; ISO 42001 missing | **BUILD** thin gap-analysis over `control_catalog` + `evidence_graph`; **add ISO 42001** to catalog. Build after first pilot asks. |
| P8 Hardening | Alembic, Postgres, remove operator bypass, SoD, signing, persistence, anchoring, MT hardening | Operator bypass control, SoD, packet persistence **done**; signing/Alembic/Postgres/anchoring **not** | **PARTIAL** — do only packet **signing** (needed by P3) now; defer Alembic/Postgres/anchoring to productionization (pilot-hosting trigger). |
| P9 Buyer Deliverables | `docs/buyer_artifacts/*` | Generators will exist after P2–P7 | **BUILD LAST**, from real outputs. |

---

## 3. Recommended build sequence & dependency map

Implement in this order; **hold at a review gate before each numbered step.**

```
P1 Gap Analysis (this doc) ──┬─► P2 Trust Score ──┐
                             │                     ├─► P4 Procurement Verification ─► P9 (procurement pkg + verification report)
        P8(signing only) ────┴─► P3 Signed/Verifiable Evidence ─┘
                                                   └─► (P5 Trust Registry)   [DEFERRED → needs P4 + pilots]
P2 ─► (P6 Insurance Readiness)   [DEFERRED → needs P2,P3,P4 + pilots]
P1 + P3 ─► (P7 Compliance Translation) ─► P9   [build after first pilot demand]
```

Hard dependencies: P3 needs packet **signing** (a P8 item) → do signing inside P3.
P4 needs P2 (score) + P3 (verifiable evidence). P5 needs P4. P6 needs P2+P3+P4. P7 needs
P1 catalog + P3 evidence. P9 needs P2–P7 + P8.

**Active scope recommendation:** P2 → P3 (incl. signing) → P4, then a minimal P9 (procurement
package + verification report). Stop. Revisit P5/P6/P7 with pilot feedback.

---

## 4. Schema changes & migration plan (additive, `m006`+)

Continue the additive `db/migration_scripts/m00N` pattern (create_all + SQLite ADD COLUMN);
no Alembic introduced now (logged as debt, §6). All new tables on the existing `Base`.

- **m006_trust_score** — new table `trust_scores`: `id, tenant_id, scope_type{action|workflow|ai_system|tenant}, scope_id, score(int), score_band, score_breakdown(JSON text), version(int), created_at`. Indexes on `(tenant_id, scope_type, scope_id)`.
- **m007_evidence_signature** — ALTER `evidence_packets` ADD `packet_signature(text)`, `signing_key_id(str)`, `expires_at(datetime)`, `verification_status(str default 'valid')`, `revoked_at(datetime null)`. (Reuses existing `packet_hash`/`version`.)
- **m008_trust_verification** — new table `trust_verifications`: `id, tenant_id, subject_type{ai_system|tenant}, subject_id, status{draft|under_review|verified|expired|revoked}, trust_score_id(fk), evidence_packet_id(fk), report_json, report_md, requested_by, reviewed_by, decided_at, expires_at, created_at`.
- **m009_iso42001_catalog** — data migration: add ISO 42001 framework + representative controls to the catalog seed (idempotent).
- *(deferred)* m010_trust_registry, m011_risk_assessment_aggregate — specified, not built.

Each migration: idempotent, forward-only, covered by a focused test, full suite must stay green.

---

## 5. API design (new surfaces)

All tenant-scoped via `principal`, gated by `require_permission`, JSON default + `?format=md` where a report applies.

- **Trust (P2)** `app/api/trust.py`: `GET /trust/score/{scope_type}/{id}`, `GET /trust/tenant/{tenant_id}`, `GET /trust/workflow/{workflow_id}` — gate `view_audit`. Response includes `score`, `score_band`, and a **`score_breakdown`** array (dimension → points earned/lost → reason). No black-box scores.
- **Evidence verify (P3)** add to `app/api/evidence.py`: `GET /evidence/verify/{packet_id}` → `{status: valid|expired|revoked|tampered, packet_hash, signature_ok, verified_at}`. Public-readable verification is acceptable (no sensitive payload); gate the *issuing* of signatures by `export_evidence`.
- **Verification (P4)** `app/api/verification.py`: `POST /verification/request` (Operator/Admin), `POST /verification/review` + `/approve` + `/revoke` (Compliance/Admin, new perm `manage_verification`). Output: verification report JSON + MD.
- **Compliance (P7, deferred)** `app/api/compliance.py`: `GET /compliance/gaps/{tenant_id}`, `GET /compliance/framework/{framework_id}`.

New permissions to seed: `view_trust_score` (or reuse `view_audit`), `manage_verification`, `publish_registry` (P5, deferred).

---

## 6. Technical debt that blocks scale

1. **No Alembic / SQLite-first.** Additive ADD-COLUMN scripts, no down-migrations, Postgres untested in CI. Blocks safe schema evolution and a hosted multi-tenant deployment. *Trigger to fix: first hosted pilot.*
2. **Global audit chain.** One chain across all tenants; per-tenant integrity is a self-hash, not an independent chain. A registry/verification product that publishes per-tenant trust needs per-tenant cryptographic integrity. *Design before P5.*
3. **Hash ≠ signature.** `packet_hash` proves integrity only if you trust the host (anyone can recompute a SHA-256). Procurement/insurance verification needs **authenticity** → asymmetric signing + key management (KMS/keyfile), and ultimately external anchoring (RFC-3161/WORM/ledger). P3 introduces signing; anchoring stays deferred.
4. **`RiskAssessment` drift.** Table exists but unused; risk lives in action metadata. Reconcile in P6 or document the split.
5. **No key management / secrets infra.** Required before signing keys or any hosted deployment.

---

## 7. Risk analysis (of doing this work)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Rebuilding existing persistence/hash (duplicate `EvidencePacket`) | High (prompt invites it) | High | §0.1/§2 — extend, don't duplicate; this doc is the guard. |
| Models in a `models/` dir → off `Base`, tables never created | High | High | Add all models to `db/models.py`. |
| Building speculative P5/P6 with no customer data | High | Medium (wasted build, wrong shape) | Defer per owner directive; gate on pilots. |
| Signing introduces key-management surface (key leak) | Medium | High | Start with a single rotatable signing key, clearly "pilot key, not production HSM"; document; never commit keys. |
| Trust Score read as a compliance guarantee | Medium | High (legal/positioning) | Enforce language guardrail; every score shows breakdown + disclaimer; band labels avoid "compliant." |
| Scope creep across 9 phases breaks the freeze & stalls pilots | High | High | Implement only P2→P3→P4; hold gates; one PR per phase, tests green. |
| Additive migrations diverge from Postgres | Medium | Medium | Keep SQLite-first now; add Postgres validation when hosting. |

---

## 8. Gate / recommendation

Phase 1 is complete. **Recommended next action:** implement **P2 Trust Score, plan-first**
(scored against the existing `evidence_graph`, fully explainable breakdown, one additive
migration, focused tests, full suite green, self-review, hold at merge gate). Then P3
(extend `EvidencePacket` + signing + verify endpoint), then P4. **Defer P5, P6, and the
heavy P8 items** (Alembic/Postgres/anchoring) until a pilot demands hosting; defer P7 until
a pilot asks for framework gap reports.

**This re-opens the feature freeze for a scoped, pilot-enabling slice only.** That is an
owner decision — do not start P2 implementation until explicitly approved.
