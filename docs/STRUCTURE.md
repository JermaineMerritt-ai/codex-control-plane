# Repository structure

| Path | Role |
|------|------|
| `app/` | Control plane API (FastAPI): routes, schemas, middleware, auth |
| `workers/` | Background jobs: queue handlers, retries, schedules |
| `connectors/` | External systems: OAuth, APIs, rate limits, errors |
| `media/` | Asset pipeline: manifests, captions, thumbnails, assembly interfaces |
| `db/` | System of record: models, migrations, repositories |
| `services/` | Business logic: content, email, approvals, policy, jobs |
| `infra/` | Deployment and environment templates |
| `tests/` | Unit, integration, API, and connector tests |
| `docker/` | Container definitions and local compose |
| `docs/` | Architecture, roadmap, connector specs, SOPs |
| `scripts/` | Bootstrap, migrations, one-off helpers |

Heavy work runs in `workers/`, not inline in HTTP handlers.
