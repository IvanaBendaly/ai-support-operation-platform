# Backend: `northstar`

FastAPI application, background worker and database migrations. Setup is in
[docs/guides/SETUP.md](../docs/guides/SETUP.md); settings are in
[docs/guides/CONFIGURATION.md](../docs/guides/CONFIGURATION.md).

## Layout

```text
northstar/
├── main.py, api.py        app assembly (create_app) and router registration
├── config.py              all settings (pydantic-settings, NORTHSTAR_* variables)
├── db.py, models.py       engine, sessions, shared models
├── domain.py, seed.py     simulated billing rules and fixtures
├── storage.py             private S3-compatible original storage
├── storage_admin.py       legacy export and orphan cleanup CLI
├── system.py              health and readiness endpoints
├── retrieval/             knowledge documents
│   ├── api.py             admin document routes
│   ├── service.py         upload, versioning, publication decisions, eligibility
│   ├── extraction.py      B1: Docling / UTF-8 extraction and sections
│   ├── verification.py    B2–B4: quality checks, LiteParse fallback, DPP subset
│   ├── fields.py          B5: LlamaExtract field confidence
│   ├── extraction_review.py  B6–B7: human verification and history
│   ├── worker.py          queue worker (extraction, then the AI review loop)
│   ├── search.py, representation.py, search_api.py   retrieval index and search
│   └── models.py          Policy, Document, Section, ExtractionRecord, ...
├── ai/                    review.py (classifier, routing), worker.py, transport.py
├── cases/                 support-case API, service, credentials
├── evaluation/            document_review.py classifier evaluation runner
└── migrations/            Alembic environment and revisions 0001–0010
tests/                     pytest suite; fixtures/ holds datasets
```

## Common commands

Run them from `backend/`, using the repository's virtual environment:

```powershell
..\.venv\Scripts\python.exe -m pytest -q                       # all tests
..\.venv\Scripts\python.exe -m pytest tests/test_extraction_verification.py -q
..\.venv\Scripts\python.exe -m ruff check . ; ..\.venv\Scripts\python.exe -m ruff format .
..\.venv\Scripts\python.exe -m alembic upgrade head            # needs NORTHSTAR_DATABASE_URL
..\.venv\Scripts\python.exe -m alembic revision --rev-id 0011 -m "short description"
..\.venv\Scripts\python.exe -m northstar.retrieval.worker      # worker loop (--once for one job)
```

Continue the numeric sequence with `--rev-id`, which produces files named
`00NN_short_description.py`. Always write a downgrade, and make it refuse to drop data
that can't be recreated.
