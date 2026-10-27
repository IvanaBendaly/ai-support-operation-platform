# Northstar — Document Upload and Preparation

This README covers only **A. Upload and validation** and **B. Extraction and
preparation**: what exists, how administrator access works, and how to run and
inspect these processes. It does not describe the rest of the support platform.

## What is implemented

| Capability | Current backend behavior |
| --- | --- |
| Upload | Individual uploads, explicit replacements, and batches of up to 10 files |
| Authentication | A configured administrator Bearer token, checked before parsing uploads |
| Validation | Request size, metadata, policy identifiers, validity dates, format and readable content |
| Formats | UTF-8 TXT/Markdown, DOCX and extractable, unencrypted PDF |
| Extraction | Direct UTF-8 decoding for TXT/MD; **Docling** for PDF/DOCX |
| Preparation | Conservative normalization, source references and sections of up to 2,000 characters |
| Persistence | Original bytes, metadata, hashes, revision, status, warnings and sections stored transactionally |
| Duplicates | Byte-hash lookup before extraction, followed by normalized-text deduplication |
| Failures | Failed extraction is recorded as `FAILED`, with an error and no sections |

Uploads are persisted as `QUEUED`. A separate database-backed worker claims them
as `PROCESSING` and commits `READY`, `FAILED`, or `DUPLICATE`. No embeddings are
created in this step. Administrator accounts/roles and frontend integration remain
unimplemented. Docling uses its native PDF pipeline (no OCR, layout/table inference
or model downloads) and its DOCX pipeline (headings and tables where available).

The frontend is a separate **session-only preview**. It uses the proposed
`document_id`/`version_id` naming, checks both fingerprints, and previews TXT/MD.
It does not send uploads to the backend. PDF/DOCX selections remain “Awaiting
worker,” and refreshing clears preview records.

## 1. How administrator access works

The operator configures `NORTHSTAR_ADMIN_TOKEN`;

The token must contain at least 32 characters. Anyone with it has access to the
administrative API; keep it private. The frontend's “Admin preview” label does not
sign you in or grant backend permissions.

- Token not configured: administrative requests return **503**.
- Backend token configured, but client token missing or incorrect: **401**.
- Token shorter than the configured minimum: application configuration fails.

The setup below generates a random token without displaying it. Keep the same
PowerShell terminal open for startup and API requests. This is a local development
setup, not a complete organization identity/permissions system.

## 2. Start the backend and database

Install/start Docker Desktop with Linux containers and Compose available. The
container route does not require local Python or Node. Run in PowerShell:

```powershell
cd C:\Users\STEAM-LB\Documents\GitHub\ai-support-ops
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `POSTGRES_PASSWORD` to a private local database password. For this development
Compose setup, an alphanumeric value avoids URL-encoding issues. If you also use
local Python commands, update the password inside `NORTHSTAR_DATABASE_URL` to
match. Preserve any existing database configuration: changing the environment
password does not change the password in an already-initialized database volume.

Generate the administrator token and request headers in this terminal:

```powershell
$tokenBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($tokenBytes)
$rng.Dispose()
$env:NORTHSTAR_ADMIN_TOKEN = [Convert]::ToBase64String($tokenBytes)
$headers = @{ Authorization = "Bearer $env:NORTHSTAR_ADMIN_TOKEN" }
$baseUrl = "http://localhost:8000"

docker version
docker compose config --quiet
docker compose up --build --wait backend worker
Invoke-RestMethod "$baseUrl/api/ready"
```

Compose starts PostgreSQL, runs Alembic migrations (including 0007), then starts
the backend and extraction worker. A
successful readiness response includes `status: ready` and `database: connected`.
No business seed data or model API key is needed for uploads and extraction.

The shell token overrides any token in `.env`. If you want it to survive a new
terminal, store the same value privately as `NORTHSTAR_ADMIN_TOKEN=...` in the
ignored `.env`, and use that same value for client requests. Do not commit `.env`.
If you regenerate/change the token, apply it to the server before using it:

```powershell
docker compose up -d --force-recreate backend
```

API documentation is at http://localhost:8000/docs. The current upload endpoints
parse multipart requests manually, so the documentation does not provide a complete
upload form or an administrator login flow. Use the commands below to exercise them.

## 3. A — Upload and validate documents

All examples below use `$baseUrl` and `$headers` from the previous section.
They create test files in a new temporary directory, leaving project files alone.

```powershell
$demoDirectory = Join-Path $env:TEMP ("northstar-upload-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $demoDirectory | Out-Null
$leaveFile = Join-Path $demoDirectory "leave-policy.md"
$accessFile = Join-Path $demoDirectory "access-policy.txt"
$expenseFile = Join-Path $demoDirectory "expense-policy.txt"

Set-Content -Encoding utf8 $leaveFile "# Employee leave policy`nEmployees may request 20 days of annual leave. Managers review requests before leave begins."
Set-Content -Encoding utf8 $accessFile "Employees must request account access through their manager. Access is removed when employment ends."
Set-Content -Encoding utf8 $expenseFile "Expense claims require receipts and manager approval. Submit claims within 30 days of the purchase."
```

### Upload a new logical document

```powershell
$upload = curl.exe -sS -H "Authorization: Bearer $env:NORTHSTAR_ADMIN_TOKEN" `
  -F "policy_id=employee-leave" -F "file=@$leaveFile" `
  "$baseUrl/api/admin/documents" | ConvertFrom-Json
$upload | ConvertTo-Json -Depth 8
$revisionId = $upload.document.id
```

For a fresh upload, expect `duplicate: false`, `document.status: QUEUED`, revision
`version: 1`, and empty `sections`. Poll inspection until the worker finishes. An unchanged repeat returns
`duplicate: true` with the existing record, even while it is queued or processing. It does not create a version relationship
or apply new metadata to that record.

The backend naming currently differs from the proposed frontend naming:

| Meaning | Backend field | Proposed/frontend field |
| --- | --- | --- |
| Stable logical identity | `policy_id`, such as `employee-leave` | `document_id` |
| Identity of one revision | Document `id`; route parameter `document_id` | `version_id` |
| Revision number | `version` | `revision` |

The API accepts `policy_id` and optional `valid_from`/`valid_until` timestamps,
not a separate title or source metadata field. Policy IDs use lowercase letters,
numbers, underscores and hyphens, start with a letter/number, and have at most
100 characters. Validity timestamps must include a timezone; expiry must be later
than the effective time. Without dates, successful content becomes effective now.

### Upload an explicit replacement

Change the content, then explicitly target the existing policy:

```powershell
Set-Content -Encoding utf8 $leaveFile "# Employee leave policy`nEmployees may request 25 days of annual leave. Managers review requests before leave begins."
$replacement = curl.exe -sS -H "Authorization: Bearer $env:NORTHSTAR_ADMIN_TOKEN" `
  -F "file=@$leaveFile" `
  "$baseUrl/api/admin/documents/policies/employee-leave/versions" | ConvertFrom-Json
$replacement | ConvertTo-Json -Depth 8
```

Expect the same `policy_id`, a new revision `id`, and an increased `version`.
Previous revisions remain stored. An unchanged file is a duplicate, not a new
revision. Using the new-document endpoint for an existing policy with changed
content returns a conflict directing you to the replacement endpoint. A replacement
for a nonexistent policy returns 404. No title/similarity matching establishes
version relationships automatically. A pending or failed replacement leaves the
previous successful version effective. A normalized-text duplicate becomes
`DUPLICATE` with `duplicate_of` pointing to the existing revision; it is not published.

### Upload a batch

Repeat `files` and `policy_ids` in matching order:

```powershell
curl.exe -sS -H "Authorization: Bearer $env:NORTHSTAR_ADMIN_TOKEN" `
  -F "policy_ids=access-policy" -F "files=@$accessFile" `
  -F "policy_ids=expense-policy" -F "files=@$expenseFile" `
  "$baseUrl/api/admin/documents/batch"
```

Each entry commits independently. Inspect every returned result: one failed entry
does not undo the others. The batch endpoint creates new policies; replacements
use the explicit replacement endpoint above.

Limits: **5 MiB per file**, **10 files per batch**, **10 MiB total batch file size**,
with a small request allowance for multipart metadata.

## 4. B — Inspect extraction and preparation

The `worker` Compose service processes the durable database queue. If running Python
locally instead, use a second terminal at the repository root with the same database
configuration: `.\.venv\Scripts\python.exe -m northstar.retrieval.worker`.
Add `--once` to process at most one available job. No Redis or queue broker is needed.

The upload response records acceptance; it does not wait for extraction. List records,
then poll a specific revision (the loop below stops waiting after 60 seconds):

```powershell
Invoke-RestMethod "$baseUrl/api/admin/documents?offset=0&limit=25" -Headers $headers
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $document = Invoke-RestMethod "$baseUrl/api/admin/documents/$revisionId" -Headers $headers
    if ($document.status -notin @("QUEUED", "PROCESSING")) { break }
    Start-Sleep -Seconds 2
}
$document | ConvertTo-Json -Depth 8
$document.sections | Format-List ordinal, source, text
```

Use `$replacement.document.id` instead of `$revisionId` to inspect the replacement.
The response includes filename, media type, timestamps, version, hashes, processing
status, errors, warnings and sections. Section references retain PDF page numbers
or TXT/MD line/heading information plus character offsets.

Processing follows this sequence:

1. TXT/MD is decoded as UTF-8. Docling converts PDF native text or DOCX content
   into structured items, retaining available page/item/heading/table references.
2. Unicode and line endings are normalized, and trailing whitespace is removed.
   Leading indentation, case, numbers, punctuation and negation are preserved.
3. Empty/unreadable output is rejected; suspicious short text can produce warnings.
4. Source units are split into sections of up to 2,000 characters.
5. SHA-256 of normalized content is checked for duplicates.
6. Sections and the final status commit together. Byte fingerprints were already
   checked before queueing; normalized duplicates retain a traceable `DUPLICATE`
   revision with no searchable sections.

Each claim has a three-minute lease. A crashed worker's claim can be recovered by
another worker; old claims cannot publish results. Conversion runs in a child process
with a two-minute timeout. After three interrupted attempts, the record becomes
`FAILED`. Timeout/invalid-file failures are terminal and inspectable. Database errors
leave the claim recoverable without publishing partial content. Exact-byte resubmission
returns the existing record, including failed records; it does not silently retry them.
The synchronous internal `ingest()` path remains available for fixtures; HTTP routes
always enqueue extraction.

Normalization detects identical resulting text, not semantic similarity or every
possible formatting-equivalent file. Ingestion does not create embeddings.

To test a real PDF, use the same single-upload command with a new `policy_id` and
`-F "file=@C:/path/to/policy.pdf"`. Use an unencrypted PDF containing selectable
text. DOCX uses the same upload endpoint with a `.docx` file. Scanned-only PDFs, corrupt
files and encrypted PDFs are rejected. DOCX references use item/heading identifiers
when page numbers are unavailable. PDF native extraction preserves page attribution
but does not reconstruct complex layouts or infer table structure.

### Inspect a failed extraction

```powershell
$brokenFile = Join-Path $demoDirectory "broken.pdf"
Set-Content -Encoding utf8 $brokenFile "This is plain text, not a PDF."
$failed = curl.exe -sS -H "Authorization: Bearer $env:NORTHSTAR_ADMIN_TOKEN" `
  -F "policy_id=broken-pdf-example" -F "file=@$brokenFile" `
  "$baseUrl/api/admin/documents" | ConvertFrom-Json
$failed | ConvertTo-Json -Depth 8
```

The initial response is `QUEUED`. Inspect the saved revision after the worker runs:

```powershell
Invoke-RestMethod "$baseUrl/api/admin/documents/$($failed.document.id)" -Headers $headers
```

Expect `status: FAILED`, `error: corrupt_pdf`, and empty sections after processing.
**HTTP 200 means the upload or duplicate was recorded, not that extraction succeeded.
Always inspect `document.status`, not just the HTTP status.** Failed attempts consume revision
numbers. Database-write failures roll back the attempt rather than leaving partial
sections or a falsely successful record.

## 5. Optional: explore the upload screens

With the backend stack running:

```powershell
docker compose up --build --wait frontend
```

Open http://localhost:8080. Use **Upload document**, **Batch upload**, or open a
record and choose **Upload replacement**. **Load examples** adds illustrative data.
TXT/MD uploads show browser-prepared sections; PDF/DOCX stay **Awaiting worker**.

These actions are preview-only: they do not use your administrator token, upload
files to the API, or display the documents saved by the commands above. Refreshing
clears preview changes. Use API inspection to verify durable backend records.

## 6. Code map and focused tests

| File | Responsibility |
| --- | --- |
| [retrieval/api.py](backend/northstar/retrieval/api.py) | FastAPI routes, administrator check, Pydantic metadata and request limits |
| [retrieval/service.py](backend/northstar/retrieval/service.py) | Explicit versioning, hash checks, ingestion status and atomic persistence |
| [retrieval/extraction.py](backend/northstar/retrieval/extraction.py) | Format checks, Docling/UTF-8 extraction, normalization and sections |
| [retrieval/worker.py](backend/northstar/retrieval/worker.py) | Durable claims, isolated conversion, timeouts and atomic completion |
| [retrieval/models.py](backend/northstar/retrieval/models.py) | Policy, revision and section relationships |
| [0004_knowledge.py](backend/northstar/migrations/versions/0004_knowledge.py) | Initial knowledge schema; 0007 adds durable extraction state |
| [Upload.tsx](frontend/src/knowledge/Upload.tsx) | Preview upload/replacement/batch interface |
| [model.ts](frontend/src/knowledge/model.ts) | Session-only validation, fingerprints, identifiers and text preparation |

Run the focused backend tests in the built container:

```powershell
docker compose exec backend python -m pytest tests/test_knowledge.py tests/test_extraction_worker.py -q
```

These tests cover supported formats, invalid files, duplicates, sections, versions,
batches, actual DOCX headings/tables, worker restart, claim fencing, bounded attempts
and transaction failures. PostgreSQL-specific tests skip unless a separate,
empty disposable test database is configured; do not point them at your application
database. Local SQLite test success does not establish PostgreSQL concurrency behavior.

For an already-installed local development environment, the equivalent is:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py tests/test_extraction_worker.py -q
```

## Troubleshooting and stopping

| Symptom | Check |
| --- | --- |
| `docker` command missing or engine unreachable | Install/start Docker Desktop, then reopen PowerShell if necessary |
| Admin API returns 503 | Configure the server token and recreate the backend container |
| Admin API returns 401 | Client header must match the running backend's token exactly |
| Upload returns 413 | File or request exceeds its size limit |
| Upload returns 422 | Check multipart field names, policy identifier and validity dates |
| File recorded as FAILED | Inspect `error` and `warnings`; scanned PDFs and OCR are unsupported |
| Record stays QUEUED | Check that the worker is running and points to the same database |
| Record stays PROCESSING after a crash | A running worker reclaims it after its three-minute lease expires |
| UI does not show an API-uploaded document | UI is a separate session preview |
| Backend does not start | Check database/migration logs with the commands below |

```powershell
docker compose logs db migrate backend worker
docker compose down
```

`down` preserves the database volume. Avoid `down -v` unless deliberately discarding
local records. Docker startup instructions describe the configured runtime; they
are not a claim that Docker/PostgreSQL verification has passed on this machine.
