# Verification and next execution

## Once Docker Desktop is running

Run from the repository root in PowerShell. Copy the example only if `.env` does
not already exist; preserve any existing configuration:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker version
docker compose config --quiet
docker compose up --build --wait
Invoke-RestMethod http://localhost:8080/api/ready
docker compose exec backend alembic check
docker compose exec backend python -m northstar.seed --as-of 2026-10-12
```

Use the current date for an interactive refund demo; use the recorded date for
repeatable fixtures. Seed runs only on empty business tables and refuses to
overwrite records. Subsequent restarts do not require another seed.

Create an empty disposable database for the PostgreSQL tests (default Compose
username shown; use your configured username if changed):

```powershell
docker compose exec db createdb -U northstar northstar_test
```

Run tests inside the backend container, using its existing connection credentials
without printing them or putting them in command history:

```powershell
docker compose exec backend python scripts/test_postgres.py
```

The helper sets only the database name to `northstar_test`. The test fixture
refuses a nonempty database, migrates it, runs tests, and removes only tables it
created. The real `northstar` business database is not the test target. If a failed
test leaves tables behind, inspect that disposable database before resetting it;
do not weaken the nonempty-database guard.

Pass evidence required before C01/C02 VERIFIED:

1. Fresh Compose build and startup without manual schema creation.
2. PostgreSQL migration upgrade, downgrade, and re-upgrade.
3. All tests pass including the three PostgreSQL tests (zero skips).
4. Seed succeeds; a second seed refuses without partial changes.
5. Frontend shows the real PostgreSQL backend state.

## Current local evidence

The project virtual environment is `.venv`. On this host Python and pnpm were
available through Codex's bundled runtimes rather than standard PATH entries.
Dependencies were downloaded and locked. Local backend tests, frontend tests,
production build, SQLite migrations, schema-drift check, seed CLI, and desktop
browser readiness refresh were executed. PostgreSQL, Docker images, and GitHub
Actions have not been executed. See `IMPLEMENTATION_STATUS.md` for exact results.

The local preview uses test-mode SQLite. This is not a substitute for PostgreSQL
row-lock/concurrency tests or container startup verification.
