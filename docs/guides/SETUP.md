# Setup guide

How to install every requirement and run Northstar, with Docker or without it.
For settings, see [CONFIGURATION.md](CONFIGURATION.md). For the workflow, see
[USAGE.md](USAGE.md).

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| [Python](https://www.python.org/downloads/) | **3.12** | Backend, worker and tests on the host |
| [Node.js](https://nodejs.org/) | **24** (see `frontend/package.json`) | Frontend on the host. Vite's dev server fails on Node older than 20.19 |
| [pnpm](https://pnpm.io/) | 11.25.0 | Frontend dependencies (`npm install --global pnpm@11.25.0`) |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Linux containers + Compose | Full stack: PostgreSQL, MinIO, API, worker, frontend |
| [Ollama](https://ollama.com/download) | optional | Local AI review with Qwen3-4B |
| OpenAI API key | optional | External AI review, only if your policy allows it |
| [LlamaCloud](https://cloud.llamaindex.ai/) account | optional | LlamaExtract field-level confidence |

Check which Pythons are installed with `py -0p`. Don't run `python -m venv .venv`
over an existing environment with another version: it re-points `.venv` and breaks
its native packages.

The Docker route needs only Docker. Python and Node are needed to run the backend or
frontend on the host, run the tests, or use the no-Docker mode.

## Install the requirements

### One command (needs Docker, Python, Node and pnpm)

```powershell
py -3.12 scripts/dev.py setup
```

This creates `.venv`, installs the locked backend dependencies and the frontend
dependencies, copies `.env.example` to `.env` if `.env` doesn't exist, and starts the
Compose stack. `python scripts/dev.py check` then runs every test, lint and the build.

### Manually

```powershell
# From the repository root
py -3.12 -m venv .venv      # must be Python 3.12 (macOS/Linux: python3.12)
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e backend

cd frontend
pnpm install --frozen-lockfile
```

On macOS or Linux, use `.venv/bin/python`. `backend/requirements.lock` pins every
Python package, including the test tools.

| Component | Package | Anything extra to install? |
| --- | --- | --- |
| Primary PDF/DOCX parser | `docling-slim` | No. Native PDF pipeline; no OCR and no model downloads |
| LiteParse fallback | `liteparse==2.17.0` | No. Self-contained wheel with a bundled PDF engine (pdfium); runs locally, OCR off |
| Object storage client | `boto3` | No. MinIO comes from Compose |
| LlamaExtract client | `httpx2` | No. LlamaExtract is a cloud API; it needs configuration only |
| OpenAI / Ollama calls | standard library | Ollama itself must be installed and the model pulled (below) |

## Set up the AI classifier (optional)

Without a provider, every document gets an `unavailable` assessment that says human
review is required. Approval still works; the AI is advisory only.

**Ollama + Qwen3-4B inside Compose.** Set these in `.env`:

```dotenv
NORTHSTAR_REVIEW__PROVIDER=ollama
NORTHSTAR_REVIEW__LOCAL_ENVIRONMENT_APPROVED=true
NORTHSTAR_REVIEW__OLLAMA_MODEL=qwen3:4b
```

```powershell
docker compose --profile local-ai up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose --profile local-ai up --build --wait
```

**Ollama installed on Windows.** Install it from ollama.com, then:

```powershell
$env:OLLAMA_NO_CLOUD = "1"; ollama serve    # terminal 1
ollama pull qwen3:4b                        # terminal 2
```

Point a host-run backend at it with `NORTHSTAR_REVIEW__OLLAMA_URL=http://127.0.0.1:11434`.

**OpenAI.** Only when your organization approves sending that sensitivity level:

```dotenv
NORTHSTAR_REVIEW__PROVIDER=auto
NORTHSTAR_REVIEW__OPENAI_API_KEY=your-private-key
NORTHSTAR_REVIEW__EXTERNAL_PUBLIC_ALLOWED=true
```

Memory, GPU, timeouts and routing rules are covered in
[DOCUMENT_REVIEW.md](../architecture/DOCUMENT_REVIEW.md).

## Run the application

### Option A: Docker Compose (full stack)

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env   # set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD (= NORTHSTAR_STORAGE__SECRET_KEY) and NORTHSTAR_ADMIN_TOKEN
docker compose up --build --wait
Invoke-RestMethod http://localhost:8080/api/ready
```

This starts PostgreSQL, the migrations (through `0010`), MinIO with a private bucket,
the API, the worker (extraction **and** AI review) and the frontend.

| URL | What |
| --- | --- |
| http://localhost:8080 | Frontend. Open **Stored documents** |
| http://localhost:8000/docs | API reference |
| http://localhost:9001 | MinIO console (local credentials only) |

`docker compose down` stops everything and keeps the data. `docker compose down -v`
deletes it.

### Option B: no Docker (local test mode)

Uses SQLite and a local folder instead of PostgreSQL and MinIO. Good for trying the
workflow; **not** a substitute for the Compose stack or the PostgreSQL tests.

```powershell
.\.venv\Scripts\python.exe scripts/local_run.py   # terminal 1: API + worker on :8000
cd frontend; pnpm dev                             # terminal 2: UI on http://localhost:5173
```

- The admin token is generated into `.test-run-local/admin-token.txt`.
- Delete `.test-run-local/` to start over.
- AI review is off unless you set `NORTHSTAR_REVIEW__*` in terminal 1 first.
- On Node older than 20.19, `pnpm dev` fails. Use `pnpm build; pnpm exec vite preview --port 5173` instead (no hot reload).

## Administrator access

The operator sets `NORTHSTAR_ADMIN_TOKEN`, at least 32 characters. Anyone holding it
has full administrative access, so keep it private. To generate one in PowerShell:

```powershell
$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
$env:NORTHSTAR_ADMIN_TOKEN = [Convert]::ToBase64String($b)
```

Store it as `NORTHSTAR_ADMIN_TOKEN=...` in the git-ignored `.env`. After changing it,
run `docker compose up -d --force-recreate backend`. Responses: **503** when no token
is configured, **401** when the client's token is missing or wrong.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `docker` not found / engine unreachable | Install or start Docker Desktop, or use Option B |
| `cannot import name '_imaging'`, `No module named 'docling'`, or every upload `FAILED` with `extraction_process_failed` | `.venv` was created or re-created with a Python other than 3.12. Check `.venv\pyvenv.cfg`, then rebuild: `py -3.12 -m venv --clear .venv` and reinstall the lockfile |
| `crypto.hash is not a function` from Vite | Node is too old. Install Node 24, or use `vite preview` (Option B) |
| Admin API returns 503 / 401 | Token not configured on the server / the client's token doesn't match |
| Upload returns 413 / 422 | Size limit / missing `title` or `sensitivity`, or a bad policy ID or date |
| Document stays `QUEUED` | The worker isn't running, or it uses a different database |
| `FAILED` with `extraction_failed` | Check the worker logs; the isolated extraction process crashed |
| `HUMAN_REQUIRED` | Expected for PDF/DOCX and short text; verify it in **Stored documents** |
| Approve button disabled / 409 | Extraction not `VERIFIED`, or the AI review hasn't finished |
| Assessment `unavailable` | No permitted AI provider for that sensitivity level |
| LlamaExtract never runs | Schema, key, project ID or sensitivity allowance missing; Highly Restricted is never sent |
| Document not in search | It must be approved, PUBLIC, enabled and within its validity dates |

```powershell
docker compose logs db migrate backend worker
```
