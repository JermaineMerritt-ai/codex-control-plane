# Control Mapping & Regulation Catalog

**Scope:** PR 5 of the Enterprise Governance Foundation — **schema + seed only**.
It adds a reference catalog of frameworks, controls, and regulations, plus the
ability to link a governed action to a control. There is no evidence-graph
logic, no UI, no connectors, and no change to the Gmail governed flow.

This capability **supports evidence collection, control mapping, audit
readiness, and governance workflows.** It does not guarantee, certify, or imply
compliance, and the seeded controls are representative top-level structures, not
a complete control catalogue.

## Data model (all tables pre-existing from PR 1)

| Table | Role |
|---|---|
| `control_frameworks` | A framework/standard (e.g. NIST AI RMF), unique by `(name, version)`. |
| `controls` | A control within a framework, unique by `(framework_id, code)`. |
| `control_requirements` | Representative requirement statements under a control, with an `evidence_type`. |
| `regulations` | A law/regulation with `jurisdiction`. |
| `industry_control_packs` | A named, tenant-scoped (or system) bundle of control ids for an industry. |
| `control_mappings` | Generic source → control link (schema only in PR 5). |
| `governed_action_control_mappings` | A governed action → control link, unique by `(tenant_id, governed_action_id, control_id)`. |

## Seeded reference catalog (idempotent, at startup)

`services/control_catalog.seed_control_catalog` is idempotent (get-or-create) and
runs at startup alongside the RBAC seed. It seeds:

- **14 frameworks**: NIST AI RMF, NIST CSF 2.0, ISO 27001, ISO 42001, SOC 2,
  HIPAA, GDPR, EU AI Act, NIST 800-53, NIST 800-171, CMMC, SOX,
  FFIEC / model risk, DORA.
- **Top-level controls** for each — the framework's real public functions /
  families / categories (e.g. NIST AI RMF → GOVERN/MAP/MEASURE/MANAGE; NIST CSF
  2.0 → GV/ID/PR/DE/RS/RC; SOC 2 → CC/A/PI/C/P). Representative top level only.
- **6 regulations** with jurisdiction (HIPAA, GDPR, EU AI Act, SOX, DORA,
  FFIEC / model risk).
- A couple of **representative control requirements** and one **system industry
  pack** (Healthcare) to exercise those tables.

All seeded descriptions use the standard language above.

## Read endpoints

The catalog is non-tenant, non-sensitive reference data, so these reads are not
permission-gated and expose no tenant/customer data:

| Route | Returns |
|---|---|
| `GET /controls/frameworks` | all frameworks |
| `GET /controls/frameworks/{id}/controls` | controls for a framework (404 if unknown) |
| `GET /controls/regulations` | all regulations |

## Governed-action → control mappings (tenant-scoped)

`create_action_control_mapping` / `list_action_control_mappings` link a governed
action to a control and are **tenant-scoped** (consistent with PR 3): a tenant
cannot see another tenant's action mappings. The `(tenant_id,
governed_action_id, control_id)` unique constraint prevents duplicate links.
These are services only in PR 5 — wiring mappings into the pipeline and the
evidence graph is a later PR.

## What this PR does NOT do

- No evidence artifacts/packets are produced (PR 6/PR 7).
- No automatic mapping of pipeline actions to controls.
- No compliance scoring, certification, or attestation.

## Tests

`tests/test_control_mapping.py`: idempotent seed (14 frameworks / 6 regulations /
stable control count on re-seed), framework + control retrieval, mapping
integrity (uniqueness + tenant scoping), the read endpoints, and a
procurement-safe language check (approved phrase used; forbidden phrases absent).
