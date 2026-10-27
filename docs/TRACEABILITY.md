# Requirements to tests

This mapping is a working checklist, not a claim of passed tests.

| Feature | Required evidence / planned test module |
| --- | --- |
| C01 | Configuration, startup, readiness, safe errors, empty-schema migration: `test_foundation.py`; frontend health/error/retry tests |
| C02 | Ownership, foreign keys, money constraints, transitions, refund idempotency, rollback, deterministic seed: `test_domain.py` |
| C03 | Markdown/text/PDF, malformed input, duplicates, versions, inactive policies: `test_ingestion.py` |
| C04 | Semantic matches, citations, active/version filters, embedding errors: `test_retrieval.py` |
| C05 | Cases/messages, idempotency, transitions, ownership, follow-up: `test_cases.py` |
| C06 | Structured output, retries/timeouts, usage, two configurations: `test_gateway.py` plus credentialed smoke |
| C07 | All five decisions, evidence conflicts, bounded attempts: `test_workflow.py` |
| C08 | Five tools, cross-account rejection, transactions, concurrency: `test_tools.py` |
| C09 | Citation/amount/plan validation, false success, fallback: `test_responses.py` |
| C10 | Approve/reject/clarify/resolve, stale and competing review: `test_review.py` |
| C11 | Authentication, roles, resource ownership, injection, budgets: `test_security.py` |
| C12 | Customer, operator, knowledge, evaluation browser journeys and visual review |
| C13 | Correlated stages, usage, audit, safe logging: `test_observability.py` |
| C14 | Standard offline suite and PostgreSQL CI, all acceptance scenarios A–G |
| C15 | 100+ labeled scenarios, isolated workflow runs, state graders, metrics, artifacts, live comparison H |
| C16 | Fresh install, Compose, migration/seed, walkthrough, documentation and screenshots |

No test listed here is evidence until its execution is recorded in the tracker.

C01 extensions (2026-10-16): `test_configuration.py` covers typed profiles,
provider references, invalid origins, real Uvicorn startup failure, malformed
environment encoding, and migration failure. `test_packaging.py` builds and
installs a wheel into an isolated directory, upgrades an empty test database,
checks readiness and schema drift, then downgrades. `scripts/tests/test_dev_command.py`
covers missing Docker and the mandatory-PostgreSQL quality gate. The frontend
also rejects malformed HTTP-success readiness payloads.

C02 completion coverage: `test_business_lifecycle.py` verifies payment/refund event
transactions, account lifecycle history, ownership/pagination, refund metadata,
reset atomicity/scope, exact repeated baselines, fresh initialization equivalence,
and expanded scenarios. `test_business_migration.py` verifies legacy data survives
0003 upgrade/downgrade and invalid legacy state rolls back the whole migration.
`test_seed_cli.py` exercises real seed/refusal/reset commands and the production
guard. `test_postgres_domain.py` additionally covers primary-database concurrent
refunds, same-key replay, and reset; execution requires a disposable PostgreSQL DB.

## C03 knowledge lifecycle

- Upload/validation/extraction: retrieval/api.py and retrieval/extraction.py.
- Metadata, sections and history: retrieval/models.py and migration 0004.
- Duplicates, transactions, scheduled validity and downstream exclusion: retrieval/service.py.
- Batch, warnings, inspection and deactivation: administrative API; tests/test_knowledge.py.
- Proof and operation contract: KNOWLEDGE.md; synthetic example policies/refunds.md.

## C04 policy retrieval

- Persisted semantic representations and atomic index: retrieval/models.py,
  retrieval/representation.py, retrieval/search.py and migration 0005.
- Active-policy synchronization, integrity checks, limits and explicit outcomes:
  RetrievalService and RetrievalSettings.
- Hybrid scoring, reranking and query reformulation: retrieval/representation.py.
- Administrative preview/rebuild: retrieval/search_api.py; existing C03 authentication.
- Fixed corpus and acceptance/failure checks: tests/test_retrieval.py and fixtures/retrieval_corpus.json.
- Portfolio proof: RETRIEVAL.md and scripts/retrieval_demo.py.

## C05 support cases

- Ownership and authentication: cases/credentials.py, cases/models.py; migration 0006.
- Validation and finite lifecycle: cases/schemas.py, cases/service.py.
- Customer-facing status, case API and administrator review: cases/api.py.
- Idempotency, history, recovery and failures: CaseService and tests/test_cases.py.
- Portfolio proof and worker contract: CASES.md and scripts/case_demo.py.


## A/B durable extraction extension

- Docling native PDF/DOCX and conservative text preparation: retrieval/extraction.py.
- Pre-extraction byte deduplication and queue submission: retrieval/service.py and api.py.
- Claims, crash recovery, timeout isolation and transactional completion: retrieval/worker.py.
- Processing state and hash index migration: 0007_extraction_jobs.py.
- Real DOCX tables/headings, durable CLI worker, duplicate exclusion, fencing and failures:
  tests/test_extraction_worker.py; API queue transition coverage: tests/test_knowledge.py.
