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
