# Implementation status

Updated: 2026-10-16. Repository initially empty; now a Git checkout.
The full implementation contract is preserved in `docs/IMPLEMENTATION_CONTRACT.md`.
No feature is VERIFIED until every mandatory completion gate passes.

| ID | Scope | Status | Dependencies | Evidence / unresolved work |
| --- | --- | --- | --- | --- |
| C01 | Foundation/configuration | IMPLEMENTED_UNVERIFIED | None | Local tests/build/browser checks pass. PostgreSQL and Compose verification pending Docker Desktop. |
| C02 | Business domain/database | IMPLEMENTED_UNVERIFIED | C01 | Models, migration, services, seed, ownership, idempotency, rollback, state machine tested locally. PostgreSQL concurrency tests await Docker. |
| C03 | Policy ingestion | NOT_STARTED | C01–02 | All acceptance criteria pending |
| C04 | Semantic retrieval | NOT_STARTED | C03 | All acceptance criteria pending |
| C05 | Support cases | NOT_STARTED | C02 | All acceptance criteria pending |
| C06 | Model gateway | NOT_STARTED | C01 | All acceptance criteria pending; live verification requires credentials |
| C07 | Workflow | NOT_STARTED | C04–06 | All acceptance criteria pending |
| C08 | Business tools | NOT_STARTED | C02, C07 | All acceptance criteria pending |
| C09 | Response verification | NOT_STARTED | C07–08 | All acceptance criteria pending |
| C10 | Human review | NOT_STARTED | C05, C08–09 | All acceptance criteria pending |
| C11 | Security | NOT_STARTED | C05–10 | Boundaries added alongside features; full gate pending |
| C12 | Dashboard | NOT_STARTED | C05–11 | C01 shell does not satisfy full dashboard scope |
| C13 | Observability/audit | NOT_STARTED | C06–10 | Foundation logging alone does not satisfy this feature |
| C14 | Automated testing | NOT_STARTED | C01–13 | Incremental tests start in C01; full suite pending |
| C15 | Evaluation/benchmark | NOT_STARTED | C01–14 | No benchmark measurements or fabricated results |
| C16 | Deployment/delivery | NOT_STARTED | C01–15 | No deployment exists |

## C01 evidence and gate

- Modules: `backend/northstar/{api,config,db,logging}.py`; `frontend/src`;
  Dockerfiles, `compose.yaml`, `.github/workflows/checks.yml`.
- APIs: `GET /api/health`, `GET /api/ready`; OpenAPI `/docs`.
- Schema: Alembic revision `0001` establishes version history; `0002` adds C02 tables.
- Completed local criteria: app starts; client starts; client calls backend;
  configuration validation; safe errors/correlation; missing database and stale
  schema return 503; SQLite migrations upgrade/downgrade/re-upgrade;
  dependency lockfiles; lint/format; developer startup instructions.
- Tests: six offline foundation tests passed. Three frontend tests passed.
  TypeScript + Vite production build passed. Uvicorn and Vite started; browser
  displayed real readiness with schema `0002` and refresh was exercised.
- `alembic check`: no new upgrade operations detected against the local test DB.
- Remaining mandatory gate: real PostgreSQL connection/migrations and fresh
  Docker Compose startup. Neither is claimed from SQLite tests or CI configuration.
- Visual review: desktop shell reviewed through the in-app browser. Full C12
  journeys, mobile review, and C16 saved screenshots are still pending.
- Docs updated: README, architecture, decisions, traceability, this tracker.

## C02 evidence and gate

- Modules: `models.py`, `domain.py`, `seed.py`; migration `0002`.
- Persistent entities: customers, accounts, plans, subscriptions, invoices,
  refunds, transactional operation/audit records.
- Internal services: owned account/subscription/invoice reads; change plan;
  refund; subscription lifecycle transitions. No unauthenticated business APIs
  exposed. Authentication and model tools are later feature gates.
- Business behavior: integer money, USD fixtures, refund window/limit/payment
  checks, duplicate protection, account-scoped idempotency, transactional audit,
  account and record locks, invalid-state rejection, terminal cancellation.
- Tests: 22 domain cases passed locally; includes injected audit failure proving
  the invoice update and refund insert roll back together. Deterministic fixtures
  recreated per test; seed rejects existing data. Seed CLI executed successfully.
- PostgreSQL tests created: competing refunds yield one committed refund;
  simultaneous same-key plan updates yield one operation and identical results.
  These have NOT executed locally.
- Docs updated: `docs/BUSINESS_RULES.md`, README, architecture, traceability.
- Remaining gate: PostgreSQL migration + concurrency verification.

## Last verification (2026-10-12)

Commands run from `backend` using the project virtual environment:

```text
python -m pytest -q                 28 passed, 3 skipped (PostgreSQL unavailable)
python -m ruff check .             passed
python -m ruff format --check .    passed
python -m alembic upgrade head     passed on local SQLite test database
python -m alembic check            no schema drift on local SQLite test database
python -m northstar.seed --as-of 2026-10-12   inserted synthetic fixtures
```

From `frontend`: `pnpm test` (3 passed), `pnpm build` (TypeScript and Vite passed).
Network package installation and the frontend bundler needed sandbox escalation.
The deprecated HTTP test-client fallback was replaced with `httpx2`.

## Resume point

The user selected local Docker and will install/start Docker Desktop. Once
available, follow `docs/VERIFICATION.md`: verify Compose and PostgreSQL migrations
before marking C01 VERIFIED. The current request selects C01 only, including its
Strong Additions. C02 code is preserved; no later features were added this turn.
The original project scope remains recorded for future feature requests.

The preview at port 5173 uses an explicitly configured SQLite **test** database,
not the production PostgreSQL environment. It demonstrates only the foundation.
No commit or push has been performed by the assistant.

## C01 follow-up (2026-10-16)

- Fixed installed-package readiness: moved migrations into the backend package
  and added wheel installation/migration/readiness regression verification.
- Added validated model/provider configuration references with disabled default
  and secret-safe startup errors; stricter origin validation; existing typed
  development/test/production profiles retained.
- Added explicit package homes for AI, retrieval, evaluation and integrations;
  no later-feature behavior implemented.
- Added `python scripts/dev.py setup` and `check [--require-postgres]`. Setup
  validates Docker/Compose, preserves configuration and waits for runtime health.
  Quality checks fail fast and isolate temporary test files between OS identities.
- Readiness rejects extra schema heads; frontend rejects malformed success
  payloads and shows the backend's environment rather than a hardcoded label.
- Added container-startup CI job and frontend health check. CI configuration
  exists but has not been executed remotely in this task.
- Real secrets: tracked environment/key-file check found only `.env.example`,
  which contains synthetic local-development credentials. No real key was added.
- Blocker: Docker executable and PostgreSQL server remain unavailable. One-command
  setup was executed and correctly failed with an actionable missing-Docker error.
  Fresh Compose installation and real PostgreSQL migration checks remain unverified.

### Current execution evidence

- `.venv/Scripts/python.exe scripts/dev.py check`: passed (46 Python tests,
  3 PostgreSQL tests skipped; 4 frontend tests; Ruff lint/format; TypeScript/Vite build).
- Packaged-wheel regression passed: isolated wheel installation, empty SQLite
  migration, readiness, schema-drift check and downgrade.
- Actual Uvicorn and Vite processes started; HTTP requests to backend health,
  frontend HTML, and frontend `/api/ready` proxy succeeded. Schema `0002`, environment `test`.
- `scripts/dev.py setup`: failed before mutation because Docker was not found.
- Failed/unverified DoD: fresh documented Docker startup; migrations against an
  empty primary PostgreSQL database. These remain mandatory, so C01 is incomplete.

## Optional candidates, not authorized for implementation

S01 retrieval improvements; S02 escalation calibration; S03 advanced approval and
recovery; S04 advanced benchmark analysis; S05 load testing; S06 evaluation gates.
All explicitly deferred features remain outside the implementation scope.
