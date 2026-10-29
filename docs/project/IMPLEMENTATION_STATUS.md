# Implementation status

Updated: 2026-10-16. Repository initially empty; now a Git checkout.
The full implementation contract is preserved in `docs/project/IMPLEMENTATION_CONTRACT.md`.
No feature is VERIFIED until every mandatory completion gate passes.

| ID | Scope | Status | Dependencies | Evidence / unresolved work |
| --- | --- | --- | --- | --- |
| C01 | Foundation/configuration | IMPLEMENTED_UNVERIFIED | None | Local tests/build/browser checks pass. PostgreSQL and Compose verification pending Docker Desktop. |
| C02 | Business domain/database | IMPLEMENTED_UNVERIFIED | C01 | Entire selected scope implemented, including metadata, billing events/lifecycle history, expanded fixtures and atomic reset. Local tests pass; PostgreSQL validation remains blocked. |
| C03 | Policy ingestion | IMPLEMENTED_UNVERIFIED | C01 | Upload, batch, extraction, versions, scheduled eligibility and deactivation implemented. PostgreSQL runtime verification pending. |
| C04 | Semantic retrieval | IMPLEMENTED_UNVERIFIED | C01, C03 | Local semantic index, hybrid/reranked search, query reformulation, lifecycle synchronization and tests implemented. PostgreSQL runtime verification pending. |
| C05 | Support cases | IMPLEMENTED_UNVERIFIED | C01, C02 | Authenticated case API, history, idempotency, finite lifecycle and lease recovery implemented. PostgreSQL concurrency verification pending. |
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
- Docs updated: `docs/architecture/BUSINESS_RULES.md`, README, architecture, traceability.
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
available, follow `docs/guides/VERIFICATION.md`: verify Compose and PostgreSQL migrations
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

## C02 selected-feature delivery (2026-10-16)

The current request selects C02 Must Build and Strong Additions only. Existing
C01/C02 interfaces are retained; no payment processor, support case workflow, or
comprehensive billing engine was added.

- Models/migration: revision 0003 adds UTC record timestamps, refund reason/state,
  billing events, and fixture version/date metadata. Additional DB checks enforce
  cancellation dates and full paid-invoice refunds. Legacy data is preserved.
- Services: existing ownership, transactions and idempotency reused; added simulated
  payment/void operations, account suspend/reactivate, owned billing/refund/lifecycle
  history. Events and audit records commit atomically with business changes.
- Fixtures: `northstar-business-v2` adds ambiguous invoices, different/disabled
  plans, boundary amounts, suspended-account invoices and scheduled bills.
- Reset: explicit CLI `--reset` and internal `reset_business`; deterministic,
  transactional, non-production, marker-guarded, and limited to business tables.
  Evaluation callers must use separate databases for concurrent scenarios.
- Small necessary C01 fix: SQLite batch-migration transaction handling preserves
  referencing legacy records and rolls back failed schema changes. PostgreSQL
  migration behavior is unchanged.
- Local verification: backend `python -m pytest -q --tb=short` passed 62 tests;
  4 PostgreSQL tests skipped. Ruff lint/format passed. Tests include real seed/reset
  subprocesses, legacy migration preservation, failed migration rollback, installed
  wheel migration/readiness, and transaction failure injection.
- Remaining gate: PostgreSQL migration/concurrency/reset execution. Docker and
  PostgreSQL are still unavailable; this feature is not marked VERIFIED.
- Portfolio proof: `docs/architecture/BUSINESS_RULES.md` contains model semantics, ER diagram,
  fixture inventory, reset commands and limits. Requirements mapping updated.


## C03 selected-feature delivery (2026-10-20)

- Migration 0004; separate knowledge models, extraction/service/admin API; bearer-token boundary.
- All Must Build and Strong Additions implemented; no OCR, external sync, or C04 vector index.
- Portfolio proof: docs/architecture/KNOWLEDGE.md and docs/policies/refunds.md.
- SQLite lifecycle, extraction, API, rollback and reset-isolation checks pass.
- PostgreSQL lifecycle/concurrency tests remain skipped: Docker/PostgreSQL unavailable.


Final C03 verification: backend pytest 79 passed, 6 skipped (including 2 C03
PostgreSQL tests); Ruff lint and format checks passed across backend and scripts.
Installed-wheel and legacy/empty migration regressions are included in that suite.

## C04 selected-feature delivery (2026-10-20)

- Migration 0005 stores an atomic semantic index snapshot with model/source/checksum metadata.
- Local corpus-trained LSA, keyword hybrid scoring, candidate reranking and deterministic
  query reformulation implement Must Build and all Strong Additions without a remote provider.
- Reusable typed retrieval service and authenticated administrative search/rebuild endpoints.
- C03 active/version/validity filtering reused before index generation and after ranking.
- Whole-section context limits, explicit empty/ambiguous/insufficient statuses and safe
  infrastructure/computation failures. No old-index fallback after a failed update.
- Fixed-corpus, lifecycle, concurrency-race, corruption, rollback and API tests added.
- Portfolio contract and runnable disposable demo: docs/architecture/RETRIEVAL.md and scripts/retrieval_demo.py.
- PostgreSQL lifecycle and concurrent index-build tests remain unverified: Docker Desktop
  and PostgreSQL are unavailable locally. No C05 workflow or distributed search was added.

Final C04 verification: backend pytest 107 passed, 8 skipped (including 2 C04
PostgreSQL checks). Ruff lint/format passed across backend and scripts.
The disposable retrieval demo ran successfully; captured output is stored in
docs/examples/retrieval-demo.json. Replacement and deactivation assertions passed.

## C05 selected-feature delivery (2026-10-20)

- Migration 0006 adds customer credentials, cases, messages, events, attempts and
  submission receipts; composite account/customer constraints protect ownership.
- Expiring/revocable opaque credentials; only hashes persisted. No public token
  issuance, authentication shortcuts or real credentials in source control.
- Customer create/read/list/history/follow-up/retry API; categories and status filters.
- Trusted worker claim/complete/fail hooks, durable leases, stale-attempt fencing,
  explicit retry and bounded recovery. Administrator inspection and human review.
- Local acceptance tests cover atomicity, ownership, duplicates, terminal states,
  failure/restart recovery, filtering, human review and business-reset protection.
- Portfolio proof: docs/architecture/CASES.md, scripts/case_demo.py and captured example output.
- No model workflow, actual action execution, review assignment, SLA or queue added.
- PostgreSQL concurrent create/claim/follow-up tests remain unverified while the
  user-selected local Docker/PostgreSQL runtime is unavailable.

Final C05 verification: backend pytest 125 passed, 10 skipped (including 2 C05
PostgreSQL concurrency tests); Ruff lint/format passed across backend and scripts.
The actual customer API demo passed and its credential-free output is captured in
docs/examples/case-demo.json. Installed-wheel and legacy/empty migration regressions
are included in the passing backend suite.


## A/B extraction extension (2026-10-27)

- Added Docling native PDF and DOCX extraction, with no OCR or model downloads.
- Added durable queued processing, expiring worker claims, isolated conversion,
  timeouts, bounded crash recovery and atomic section/status completion (0007).
- Added indexed pre-extraction byte-hash lookup, PostgreSQL same-hash submission
  serialization, normalized duplicate status/references and retrieval exclusion.
- HTTP uploads now return QUEUED; poll document inspection for the final state.
  The synchronous service path remains for fixtures. Frontend integration is unchanged.
- Full backend checks: 141 passed, 11 skipped; Ruff and dependency checks pass.
  Docker/PostgreSQL are unavailable here; no container/primary-database execution claimed.


## C/D private-storage and document-review extension (2026-10-29)

- Implemented S3-compatible original storage (MinIO development services), opaque keys,
  staged verified legacy export, durable orphan reservations and conservative cleanup.
- Added required sensitivity/title, immutable classification, policy-first OpenAI/Ollama
  routing, Qwen3-4B configuration, validated output/citations and durable review attempts.
- Persisted assessments and document processing/decision events. Human approval is required
  independently of model output; only approved PUBLIC material enters existing retrieval.
- Added connected Stored documents frontend with real upload, inspection and human decisions.
- Added Ollama native/Docker instructions, cloud storage and backup boundaries, evaluation
  runner and 12 draft-labeled synthetic examples. No manual-label validation or model-quality
  result is claimed. Expand to 50–100 representative reviewed examples before a baseline.
- pgvector remains future work; no vector migration was introduced. Shared administrator
  credentials are not per-document clearance or individual identity management.
- Runtime verification evidence for this change is recorded after the test run; live
  PostgreSQL/MinIO/Ollama/OpenAI checks require those configured services.

### C/D verification evidence

- Full backend + developer-command suite: **180 passed, 13 skipped** (PostgreSQL and
  explicit live MinIO integration unavailable). Includes verified legacy export,
  migration schema parity, installed-package checks, publication eligibility, routing,
  fabricated citations, failed providers, review leases/rollback and real local HTTP
  subprocess timeout/redirect checks.
- Frontend: **16 passed**; TypeScript + Vite production build passed.
- Ruff lint/format and `pip check` passed. Compose YAML parsed; Docker runtime itself
  is unavailable, so parsing is not claimed as container startup verification.
- Evaluation dry-run validated 12 draft examples without model calls. No live-model
  quality, latency or cost claim; human labels and provider runs remain required.
- CI now includes a private MinIO upload/read-back/anonymous-denial probe. CI has not
  been executed remotely in this task. The filesystem adapter and S3 contract stubs
  do not substitute for the live object-store or primary PostgreSQL checks.


## BR-01 Architecture B: extraction verification (2026-10-29)

Continued from an interrupted session. B1–B7 code (verification, fields, extraction_review,
migration 0010, verification UI) existed but was untested and partly broken.

- Fixed: `fields.py` imported `httpx` (not installed; the dependency is `httpx2`), so every
  isolated worker extraction crashed into `extraction_failed`. Import is now lazy `httpx2`.
- Fixed: an empty LiteParse result for an unreadable PDF was selected as READY content.
  LiteParse now raises `empty_or_unreadable_text`; a FAILED fallback is never selected.
- Fixed: every extraction decision purged the retrieval index; now only when published
  content is withdrawn (matching publication decisions).
- Added highlighting of passages named by failing/unevaluated checks (B6), Compose and
  `.env.example` extraction settings, and docs/architecture/EXTRACTION_VERIFICATION.md (criteria map).
- Updated pre-existing tests that predated the verification gate; downgrade test now
  asserts both the provenance and original-storage guards.
- Known behavior: with OCR off Docling reports NaN OCR scores, so all Docling PDFs are
  UNCERTAIN → LiteParse → human. DPP visual rules require a human for PDF/DOCX anyway.

### Verification evidence

- Backend: **208 passed, 13 skipped** (30 new BR-01 tests). Ruff lint/format passed.
- Frontend: **18 passed**; TypeScript + Vite production build passed (fixed a TS error in
  `Connected.tsx`). Run with `npm run` here because `pnpm` was not on PATH.
- Not verified: live LlamaExtract (mock transport only; no credentials), any confidence
  floor (no evaluated examples), PostgreSQL/MinIO/Compose runtime.
- README rewritten: prerequisites (Python 3.12, Node 24, pnpm 11.25.0, Docker), full install,
  LiteParse (bundled wheel, nothing extra), AI classifier setup, LlamaExtract configuration,
  no-Docker mode (`scripts/local_run.py`, SQLite + folder storage, test mode only), current
  workflow and code map. The README API walkthrough and evaluation dry-run were executed
  against the local test-mode server; Docker, Ollama, OpenAI and live LlamaExtract steps were not.

## Repository organization (2026-10-29)

- Docs moved to `docs/guides/` (setup, configuration, usage, verification), `docs/architecture/`
  and `docs/project/` (this tracker, contract, traceability); `docs/README.md` indexes them.
  All relative links were rewritten and checked (0 broken).
- README is now a quick start: description, GIF, features, tech stack, Mermaid architecture,
  repository layout, docs map, technical challenges. Per-app `backend/README.md` and
  `frontend/README.md`; `CONTRIBUTING.md`; GitHub issue and pull-request templates.
- Screenshots and a workflow GIF in `docs/assets/`, recorded from the running local app.
- Committed pytest output (`.test-b-first/`) removed; `.test-*/` and `compose.override.yaml` ignored.
- Fixed: the UI sent section `id`/`ordinal` with corrections, so every CORRECT returned 422.
  The test fixture now mirrors API sections. Found while recording the GIF.
- `.venv` had been re-created with Python 3.11 over the 3.12 install, breaking Pillow/Docling
  and failing every extraction. It was rebuilt from the lockfile on Python 3.12;
  `scripts/dev.py setup` now refuses a non-3.12 interpreter or environment.
- Verification: backend + scripts 211 passed, 13 skipped; frontend 18 passed; build, Ruff passed.
