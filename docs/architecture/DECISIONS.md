# Implementation decisions

| ID | Decision | Reason / consequence |
| --- | --- | --- |
| D01 | Single synchronous FastAPI/SQLAlchemy service | Easy transaction reasoning; sync routes execute outside the event loop. No workers until required. |
| D02 | PostgreSQL runtime; SQLite unit tests plus PostgreSQL CI | Fast offline tests do not substitute for database-specific verification. |
| D03 | Alembic migrations, no startup `create_all` | Missing or outdated schema makes readiness fail instead of hiding deployment mistakes. |
| D04 | React/TypeScript/Vite, plain CSS | Small dependency surface and an accessible, consistent dashboard. |
| D05 | Separate liveness and readiness | Database failure must not be reported as healthy readiness. |
| D06 | Explicit environment configuration, secret-safe errors | Configuration should fail early without printing credentials. |
| D07 | Package migrations with the backend | The installed wheel and source checkout must compute readiness from the same schema history. |
| D08 | One small Python developer command | Cross-platform Docker setup and local quality checks; no additional task framework. |
| D09 | Disabled model configuration by default | Validate future provider references and secret handling without introducing model execution into C01. |

Dependency references reviewed on 2026-10-12:

- [FastAPI version guidance](https://fastapi.tiangolo.com/deployment/versions/)
- [SQLAlchemy 2 tutorial](https://docs.sqlalchemy.org/en/20/tutorial/)
- [Alembic migration tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Vite setup](https://vite.dev/guide/)

Use Python 3.12+ and Node 24 LTS. Resolve compatible stable versions within major
constraints and lock installed versions after tests. Do not independently select
a Starlette version outside FastAPI's dependency constraints.
