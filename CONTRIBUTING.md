# Contributing

## Set up

Follow [docs/guides/SETUP.md](docs/guides/SETUP.md). The short version without Docker:

```powershell
py -3.12 -m venv .venv      # must be Python 3.12 (macOS/Linux: python3.12)
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e backend
cd frontend; pnpm install --frozen-lockfile
```

## Where things go

| Change | Location |
| --- | --- |
| Backend feature | `backend/northstar/<area>/` (`retrieval`, `ai`, `cases`, ...). See [backend/README.md](backend/README.md) |
| Schema change | A new Alembic revision in `backend/northstar/migrations/versions/`, with a downgrade |
| Backend test | `backend/tests/test_<area>.py`; shared fixtures in `conftest.py` and `knowledge_fixtures.py` |
| Frontend feature | `frontend/src/`, with its `*.test.tsx` next to the component. See [frontend/README.md](frontend/README.md) |
| New setting | `backend/northstar/config.py`, `.env.example`, [CONFIGURATION.md](docs/guides/CONFIGURATION.md) and, if containers need it, `compose.yaml` |
| Design explanation | `docs/architecture/`, linked from [docs/README.md](docs/README.md) |
| Screenshots | `docs/assets/` |

## Before you open a pull request

```powershell
python scripts/dev.py check
```

This runs Ruff lint and format checks, the backend and script tests, the frontend
tests and the production build. CI (`.github/workflows/checks.yml`) runs the same
checks. Also:

- Add or update tests for behavior you change.
- Update the docs that describe it, and the status tracker
  ([IMPLEMENTATION_STATUS.md](docs/project/IMPLEMENTATION_STATUS.md)) for feature work.
- Never commit secrets, `.env`, `compose.override.yaml`, or real documents.

## Conventions

- **Python:** Ruff with a line length of 100 (`backend/pyproject.toml`). Use
  `DomainError` for expected failures. Fail closed: a missing check, score or
  permission must never count as a pass.
- **TypeScript:** strict mode. Components and their tests live side by side.
- **Branches and commits:** branch from `main` (`feature/...`, `fix/...`, `docs/...`).
  Commit subjects are imperative and under 72 characters, for example
  `Add LiteParse fallback for empty PDFs`.
- **Docs:** fenced code blocks always name a language (`powershell`, `python`, `text`,
  `mermaid`, ...); diagrams use Mermaid; links are relative.
