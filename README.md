# Northstar Cloud — AI Support Operations

A phased implementation of a policy-grounded support system for a fictional SaaS
business. The intended product combines case management, controlled business
actions, human review, auditable AI decisions, and reproducible model evaluation.

**Current stage: C01 foundation and C02 internal business domain implemented;
PostgreSQL/Docker verification pending. The complete product is not ready.** See
[implementation status](IMPLEMENTATION_STATUS.md) and the preserved
[implementation contract](docs/IMPLEMENTATION_CONTRACT.md).

## Run the foundation

Prerequisites: Docker Engine with Compose v2. Copy `.env.example` to `.env` and
choose a local database password (URL-encode special characters when used in a
database URL; simple alphanumeric passwords avoid Compose URL interpolation issues).

```sh
cp .env.example .env
docker compose up --build
```

Open http://localhost:8080. OpenAPI documentation is at http://localhost:8000/docs.
Compose waits for PostgreSQL, runs migrations in a separate one-shot service,
then starts the backend and frontend. Failed migrations prevent backend startup.

With Python 3.12+, Node 24, pnpm 11 and Docker Compose installed, one-command setup
is `python scripts/dev.py setup`. It preserves an existing `.env`, otherwise
copies the example, creates the local virtual environment and installs locked
backend/frontend development dependencies. It checks the Docker engine and Compose
configuration, builds, migrates, starts, and waits for the API and frontend health checks. It fails with
a nonzero exit status if any step fails.

```sh
docker compose run --rm migrate
docker compose logs backend
docker compose restart backend frontend
docker compose down
```

`down` preserves the database volume. Do not use `down -v` unless deliberately
discarding local data. This is a localhost development configuration, not a
public deployment. No deployment or live model benchmark is claimed.

## Local development

Python 3.12+, Node 24, pnpm 11, and PostgreSQL 17 are required. With PostgreSQL
running, execute from the repository root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1; Unix: source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e backend
```

Set `NORTHSTAR_DATABASE_URL` to your PostgreSQL SQLAlchemy URL, or copy `.env.example`
to `backend/.env` for backend commands. The setting is mandatory. `.env` files
are ignored. From `backend`:

```sh
alembic upgrade head
uvicorn northstar.api:create_app --factory --reload --no-access-log
```

Alternatively, keep `.env` at the repository root and run both commands there:
`python -m alembic -c backend/alembic.ini upgrade head` and
`python -m uvicorn northstar.api:create_app --factory --reload --no-access-log`.
The environment file is read from the current working directory. Real environment
variables override `.env`. The startup error identifies invalid fields without
printing their submitted values.

From `frontend`, in another terminal:

```sh
pnpm install --frozen-lockfile
pnpm dev
```

Vite proxies `/api` to port 8000. The shell displays real database readiness and
offers a retry after failures. `/api/health` is process liveness; `/api/ready`
checks database connectivity and schema revision. It returns HTTP 503 when
the database is unavailable or needs migration. Requests have generated
correlation IDs; errors do not echo credentials or validation input values.

## Tests and checks

After installing the local backend/frontend dependencies, run every local quality
check from the root with `python scripts/dev.py check`. This runs backend and
developer-command tests, Ruff lint/format checks, frontend tests, TypeScript, and
the frontend production build. It stops on failure. PostgreSQL tests are skipped
when no test URL is set; use `python scripts/dev.py check --require-postgres` for
a release gate that refuses to proceed without that database configuration.

```sh
cd backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
cd ../frontend
pnpm test
pnpm build
```

Offline tests use disposable SQLite databases. Set `NORTHSTAR_TEST_DATABASE_URL`
to an **empty disposable PostgreSQL database** to run the PostgreSQL migration
test. GitHub Actions provisions that database. A configured CI workflow is not
evidence of a completed CI run. No paid model calls are made by standard tests.

## Configuration

| Variable | Purpose |
| --- | --- |
| `NORTHSTAR_DATABASE_URL` | Required SQLAlchemy URL; runtime uses `postgresql+psycopg://` |
| `NORTHSTAR_ENVIRONMENT` | `development`, `production`, or `test`; SQLite only in test |
| `NORTHSTAR_ALLOWED_ORIGINS` | JSON list of explicit origins; HTTPS required in production |
| `NORTHSTAR_LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose database initialization |
| `NORTHSTAR_TEST_DATABASE_URL` | Disposable PostgreSQL integration-test database |
| `NORTHSTAR_MODEL_PROVIDER` | `disabled` (default) or `openai`; configuration reference only in C01 |
| `NORTHSTAR_MODEL_NAME` | Required nonblank model identifier when provider is configured |
| `NORTHSTAR_PROVIDER_API_KEY` | Required secret when provider is configured; never returned by health APIs |
| `NORTHSTAR_MODEL_TIMEOUT_SECONDS` | Positive number up to 120; default 30 |
| `NORTHSTAR_MODEL_MAX_OUTPUT_TOKENS` | Integer 1–16384; default 1024 |

Typed environment profiles share one settings class: development uses PostgreSQL
and explicit local origins; test additionally permits SQLite; production requires
PostgreSQL and explicit HTTPS origins. For production, set
`NORTHSTAR_ENVIRONMENT=production` and
`NORTHSTAR_ALLOWED_ORIGINS=["https://support.example.com"]` together with the
deployment's database URL. Model configuration does not enable model execution:
that belongs to C06. No live provider dependency affects C01 readiness.

## Architecture and remaining delivery

See [architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md), and
[requirements-to-tests mapping](docs/TRACEABILITY.md). Routes, configuration,
database access, migrations, tests, and UI have separate homes. Domain services,
retrieval, model gateway, review, and evaluation will be implemented in dependency
order. Financial mutations must commit with audit records; model outputs cannot
grant permissions or establish a successful operation.

The internal business services persist accounts, subscriptions, invoices, refunds,
and operation audit records. They enforce ownership, valid plan/status changes,
refund eligibility, idempotency, and transactional consistency. See
[business rules](docs/BUSINESS_RULES.md). These are not yet customer-facing APIs.

From `backend`, after migration, seed an empty development database with:

```sh
python -m northstar.seed --as-of 2026-10-12
```

Use today's date for an interactive demo or the fixed date for repeatable tests.
Seed refuses existing business records and production environments. For an already
seeded **disposable** development/test database, add `--reset` to restore the
versioned baseline atomically, including billing history and idempotency records.
There is no reset HTTP endpoint. Tests build fresh isolated fixtures. Follow
[Docker verification steps](docs/VERIFICATION.md) once Docker Desktop is running.

C02 also supplies internal payment/void simulation, account suspension/reactivation,
owned billing/lifecycle history reads, refund reasons/states, and record timestamps.
See the [business model, relationship diagram, and scenario inventory](docs/BUSINESS_RULES.md).

Customer authentication, support cases, semantic retrieval, AI interactions,
approvals, and benchmarks are not yet available.
There are no measured model/cost/latency tradeoffs to report. The later feature
gates cover these, along with screenshots and the complete portfolio walkthrough.
Optional enhancements are listed in the tracker and will not be added silently.

## Knowledge administration (C03)

See [knowledge lifecycle and upload examples](docs/KNOWLEDGE.md). Apply migration 0004
and configure NORTHSTAR_ADMIN_TOKEN to enable the administrative document API.

## Policy retrieval (C04)

See [retrieval service, configuration and demo](docs/RETRIEVAL.md). Migration 0005
adds the persisted local semantic index. The administrative search API and internal
service synchronize active policies before returning bounded, attributed evidence.
