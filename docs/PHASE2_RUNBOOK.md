# Phase 2 Runbook — Pilot-Grade Governance Control Plane

Reflects the merged Phase 2 state (PR #9 workflow + PR #10 console/seed). This is
the **canonical app**; `codexdominion-schemas` is a spec/reference registry only
(see its `CANONICAL_APP.md`).

CodexDominion **supports evidence collection, control mapping, audit readiness,
and governance workflows.** It does not certify, guarantee, or determine
compliance, and is not a regulatory authorization.

## What Phase 2 delivers
The pilot loop, end to end, in a browser:

> **login (API key) → submit governed action → policy evaluation → risk
> classification → approval if needed → immutable audit trail → evidence packet
> export.**

- Pilot workflow: **AI Vendor / Automation Governance Review** (`services/governance_workflow.py`).
- Deterministic risk classifier (`services/risk_service.py`).
- Browser console at **`/console`** (`app/static/console.html`).
- Idempotent seed (`scripts/seed_pilot.py`).
- Reuses Phase 1: policy, approvals, tamper-evident audit chain, control catalog,
  evidence graph, evidence-packet export. **No second engine.**

## Install
```bash
git clone https://github.com/JermaineMerritt-ai/codex-control-plane
cd codex-control-plane
python -m venv .venv && . .venv/Scripts/activate    # Windows; or source .venv/bin/activate
pip install -e ".[dev]"
```

## Environment variables
| Var | Default | Pilot setting |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./local.db` | use the **same value** for seed + API (e.g. `sqlite:///./pilot.db`) |
| `OPERATOR_API_KEY` | unset | **leave unset** for the console demo (RBAC via `X-Api-Key` is the auth path) |
| `REQUIRE_RBAC_FOR_OPERATOR` | `false` | leave `false` for the demo; set `true` to harden the no-key bypass |
| `GMAIL_MODE` | `stub` | `stub` (the governance pilot does not need live Gmail) |

## Seed demo data (idempotent)
```bash
export DATABASE_URL="sqlite:///./pilot.db"
python -m scripts.seed_pilot
```
Creates tenant `pilot-tenant`, a control catalog, a sample run, and one user +
API key per role. Re-running is safe (existing rows reused).

| Role | Demo key (header `X-Api-Key`) | Can |
|---|---|---|
| Admin | `pilot-admin-key` | all except manage_users |
| Operator | `pilot-operator-key` | **submit** governed actions |
| Reviewer | `pilot-reviewer-key` | **approve / reject** |
| Auditor | `pilot-auditor-key` | **view + export** evidence |

> Demo keys are **fixed and non-production** — rotate before any real/external use.

## Run the control console
```bash
export DATABASE_URL="sqlite:///./pilot.db"   # same DB as the seed
python -m uvicorn app.main:app --port 8099   # do NOT set OPERATOR_API_KEY
```
Open **http://127.0.0.1:8099/console** (API docs at `/docs`).

## Run the pilot workflow (in the console)
1. Paste `pilot-operator-key` → fill the form → **Submit review**.
   Policy + deterministic risk auto-evaluate; medium/high risk creates an approval.
2. Paste `pilot-reviewer-key` → **Approve** (or Reject).
3. Paste `pilot-auditor-key` → **Export JSON / Markdown**.

Equivalent API:
```
POST /workflows/vendor-governance-review     # Operator/Admin
GET  /workflows/runs   |   GET /workflows/runs/{id}
POST /approvals/{id}/approve | /reject       # Reviewer/Admin/Compliance
GET  /evidence/packets/export/{id}?format=json|md   # Auditor/Admin
```

## How to export evidence
`GET /evidence/packets/export/{governed_action_id}?format=json|md` (header
`X-Api-Key`). The packet includes: governed action(s), policy decision, risk,
approvals, **workflow step audit events** (surfaced as of PR #9), audit-chain
verification status, mapped controls/regulations, evidence artifacts, and
identified evidence gaps.

## Tests
```bash
pytest          # 121 passed, 2 skipped (the 2 skipped are opt-in Gmail live tests)
```

## Known limitations
- **Migrations:** no Alembic; schema via `create_all` + optional additive SQLite
  helpers. Production needs a real migration tool.
- **Database:** SQLite by default; PostgreSQL is supported by the code but not
  exercised in CI.
- **Operator bypass:** the no-API-key path is full access by default (that is why
  the console demo runs without `OPERATOR_API_KEY`). Harden with
  `REQUIRE_RBAC_FOR_OPERATOR=true` + provisioned principals for real use.
- **Audit chain:** global; per-tenant verification is self-hash. Tail-truncation
  is not self-detecting (external anchoring is future work).
- **Evidence packets:** generated on demand, not persisted.
- **Console:** minimal/demo-grade (usability, not a production UI). Single-process
  worker; Gmail is the only reference connector.
