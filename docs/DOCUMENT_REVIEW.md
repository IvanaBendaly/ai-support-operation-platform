# Private storage and document review (C / D)

Original files live in a private S3-compatible bucket: MinIO in local development,
S3-compatible storage in deployment. PostgreSQL stores opaque `storage_key` values,
metadata, versions, extracted sections, assessments and processing/decision events.
There are no public or presigned file URLs and no download endpoint. The filesystem
adapter is test-only. pgvector embeddings are reserved for the later retrieval
implementation; the existing local LSA index remains a compatibility feature and now
accepts only human-approved PUBLIC versions. No pgvector schema is claimed here.

## Runtime flow and code map

1. `retrieval/api.py` requires the administrator bearer token, title and sensitivity.
2. `retrieval/service.py` checks metadata, reserves an opaque object key, writes the
   original, and commits the version. Duplicate uploads do not create relationships.
3. `retrieval/worker.py` fetches bytes by key and verifies SHA-256, then extracts and
   verifies sections ([EXTRACTION_VERIFICATION.md](EXTRACTION_VERIFICATION.md)).
4. `ai/worker.py` claims a separate durable review attempt once extraction is VERIFIED.
5. `ai/review.py` checks the sensitivity of **both versions** before constructing a
   provider. A bounded current/previous comparison is classified and citations checked.
6. The assessment commits without approving anything. A human calls the decision API.
7. Retrieval requires READY + APPROVED + effective/enabled + PUBLIC. An approved newer
   revision supersedes the earlier one when effective, even if the newer revision is
   private and therefore cannot enter the public index. Failed/rejected replacements
   leave the current version in place. Deactivation does not resurrect older content.

Models are in `retrieval/models.py`; storage is in `storage.py`; maintenance commands
are in `storage_admin.py`; migrations are `0008` and `0009`. `Document.id` still means
a version ID; `Policy.id` is the logical identity. The support-workflow gateway settings
(`NORTHSTAR_MODEL_*`) are separate from document review (`NORTHSTAR_REVIEW__*`).

The connected React screen is **Stored documents** in the sidebar. It supports real
uploads, inspection, refresh, assessments and approve/reject/request-changes decisions.
The original Documents/Review queue screens remain explicitly labeled session previews.
The connected screen never stores its token in localStorage. It requires sensitivity
selection with no default. API documentation is also available at `/docs`.

## What the classifier means

The question is: **Does this document need additional human attention due to potential
quality, completeness, inconsistency or policy-change risks?** It does not decide if a
document is good, safe, or authorized for publication.

Both providers use the same Pydantic-validated JSON schema:

| Field | Meaning |
| --- | --- |
| `needs_review` | Additional attention beyond the mandatory publication review |
| `review_reasons` | Extraction quality, missing information, possible policy contradiction, unexpected change, ambiguity, incomplete comparison |
| `risk_level` | `low`, `medium`, `high` review priority |
| `explanation` | Brief assessment, not hidden reasoning |
| `supporting_references` | Exact quotes and known section IDs from the supplied passages |
| `provider`, `model_id` | Set by trusted code, not accepted from model output |
| `assessment_status` | `completed`, `failed`, `unavailable` |
| `metrics` | Latency, validity and token usage when the provider supplies it |
| `prompt_version` | Versioned prompt contract for reproducible evaluation |

Invalid JSON/schema, invented references, refusals, errors or timeouts become failed
assessments with `needs_review=true`, never low-risk success. Unavailable/prohibited AI
also requires human inspection. Deterministic quality warnings and truncated comparison
inputs force review even if the model returns low risk. Contradictions must reference
both versions. Exact-quote validation establishes source fidelity, not semantic correctness.

No model has publication permissions or tools. Document text is explicitly treated as
untrusted evidence. OpenAI uses the Responses API with `store=false`; Ollama uses
`/api/chat`, a JSON schema, `think=false`, and bounded generation. HTTP redirects and
environment HTTP proxies are disabled. Provider responses and exceptions are not logged.

## Sensitivity and routing

| Classification | OpenAI | Ollama | Publication |
| --- | --- | --- | --- |
| Public | Credentials + explicit public processing setting | Approved local environment | Human approval |
| Internal | Credentials + explicit internal organization policy | Approved local environment | Human approval; no current search indexing |
| Confidential | Disabled unless explicit organization exception | Approved private environment | Human approval; no current search indexing |
| Highly Restricted | **Never** | Both local and restricted-local approval required | Mandatory human approval; no current search indexing |
| Missing / unknown | Never | Never | Resolve classification first |

`provider=auto` prefers OpenAI only if credentials and the relevant policy permit it;
otherwise it selects an approved local provider before any call. `provider=ollama`
never calls OpenAI. `provider=openai` never silently changes providers. Any call failure
terminates that assessment; there is **no local-failure-to-external fallback**.
The default is `provider=disabled` and all permissions false.

Sensitivity is required for each upload and immutable after assignment. Replacements
cannot lower the existing policy classification. Legacy UNCLASSIFIED records can be
classified once by an administrator with a recorded reason. Highly Restricted documents
always need human approval regardless of the model recommendation.

Confidential/Highly Restricted uploads require
`NORTHSTAR_STORAGE__RESTRICTED_ENVIRONMENT_APPROVED=true`. This is an operator
attestation that storage, extracted-text PostgreSQL data, worker temporary directories,
administrator workstations, backups and logs are approved. It does not configure encryption,
IAM or backup security.
Do not set it for the default development stack and then upload real restricted data.

The current shared administrator token grants access to all administrative records;
it is not per-document clearance or individual identity management. Operator security
must restrict holders to authorized reviewers. Audit actor is `administrator`, not a
verified person's name. Responses use `Cache-Control: no-store`; previews are authenticated;
restricted previews require the approved environment. No source text, quotations or
credentials are written to application logs. Review explanations/citations are sensitive
database records. Restrict database access and encrypt coordinated DB/object backups.
No confidential data enters the current embeddings/retrieval index; future ACL-aware
retrieval must enforce permissions at evidence use, not just when vectors are removed.

## Run locally with Docker Compose

Install Docker Desktop with Linux containers. From the repository root, copy
`.env.example` to `.env` **only if `.env` does not already exist**. Set a private
`NORTHSTAR_ADMIN_TOKEN` of at least 32 characters and replace local passwords.
Keep `MINIO_ROOT_PASSWORD` and the host-side `NORTHSTAR_STORAGE__SECRET_KEY` aligned.

For a fresh database:

```powershell
docker compose up --build --wait
```

This starts PostgreSQL, migrations, MinIO, private-bucket initialization, API, worker,
and frontend. UI: `http://localhost:8080`. MinIO console: `http://localhost:9001`.
Ports are loopback-bound. Local credentials are for development only. The initializer
explicitly disables anonymous bucket access. Do not expose the console publicly.
The pinned community MinIO release is a local development dependency, not a claim of
current security maintenance for production.

For Qwen3-4B, set in `.env`:

```dotenv
NORTHSTAR_REVIEW__PROVIDER=ollama
NORTHSTAR_REVIEW__LOCAL_ENVIRONMENT_APPROVED=true
NORTHSTAR_REVIEW__OLLAMA_MODEL=qwen3:4b
```

Then:

```powershell
docker compose --profile local-ai up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose --profile local-ai up --build --wait
docker compose exec ollama ollama list
```

Compose uses `http://ollama:11434` internally and sets `OLLAMA_NO_CLOUD=1`.
Pulling weights requires internet access; provision the weights before moving to an
offline environment. The default service is CPU-only, limited to 8 GiB; it may be slow.
4B refers to model size, not a guarantee of RAM requirements or latency. Increase Docker
memory if needed; reduce document input budget or raise the bounded timeout (max 120s)
after measuring. A GPU requires the appropriate Docker GPU runtime; for NVIDIA an
override can add `gpus: all` to the Ollama service. Do not add GPU requirements to the
default CPU setup. Protect the model volume and prevent inference-time internet egress
in an approved deployment. The local server is not automatically a security boundary.

## Run Ollama directly on Windows

Install Ollama from its official download. Set the environment variable before restarting
the Ollama server (quit the existing desktop service first if it already owns port 11434):

```powershell
$env:OLLAMA_NO_CLOUD="1"
ollama serve
```

In a second terminal:

```powershell
ollama pull qwen3:4b
ollama list
```

For a host-run backend/worker, set `NORTHSTAR_REVIEW__OLLAMA_URL=http://127.0.0.1:11434`
and the same provider/local-approval settings above. Run the API and worker from
`backend` using the project virtual environment and an environment containing the root
`.env` values. For a Docker worker talking to host Ollama, use a Compose override that
sets `NORTHSTAR_REVIEW__OLLAMA_URL=http://host.docker.internal:11434` on the worker.
The URL validator allows loopback/private IPs and the documented Docker hostnames only;
it rejects public Ollama endpoints and cloud model tags.

## Configure OpenAI or automatic selection

Set only policy permissions your organization has approved. For public documents:

```dotenv
NORTHSTAR_REVIEW__PROVIDER=auto
NORTHSTAR_REVIEW__OPENAI_MODEL=gpt-4o-mini
NORTHSTAR_REVIEW__OPENAI_API_KEY=your-private-key
NORTHSTAR_REVIEW__EXTERNAL_PUBLIC_ALLOWED=true
```

For an approved local alternative, also enable `LOCAL_ENVIRONMENT_APPROVED` and start
Ollama. Internal permission and confidential exception are separate settings, both false
by default. No setting permits external processing of Highly Restricted content.
Model choice is configurable; use a model supporting Structured Outputs and evaluate it.

OpenAI says API data is not used for training by default, but retention and processing
controls still apply. `store=false` is not a guarantee of zero retention. Organizational
approval is required before external processing of private information.

## API example and human decision

Use the administrator token in an environment variable, never in a URL:

```powershell
curl.exe -H "Authorization: Bearer $env:NORTHSTAR_ADMIN_TOKEN" -F "policy_id=refund-policy" -F "title=Refund policy" -F "sensitivity=PUBLIC" -F "file=@docs/policies/refunds.md" http://localhost:8000/api/admin/documents
```

Poll `GET /api/admin/documents/{id}`. READY means extraction finished, not publication.
Wait for `review_status=DONE`, inspect the assessment/sections, then submit:

```json
{"decision":"APPROVED","reason":"I checked both revisions and confirmed the change."}
```

to `POST /api/admin/documents/{id}/decision`. Other decisions are REJECTED,
CHANGES_REQUESTED and DELETED. A reason is mandatory, including when overriding an AI
warning or approving after an unavailable/failed assessment. Requested changes are
submitted as a replacement revision. Deleted records are immediately ineligible but
files and audit records are retained for the organization's retention process.
Batch uploads require parallel `files`, `policy_ids`, `titles`, `sensitivities` fields.

## Existing database migration and storage cleanup

Do not drop binary originals before verifying their external copies. Back up the
database first and stop API/worker writers. With existing documents, `upgrade head`
deliberately refuses until the export has completed:

```powershell
docker compose stop backend worker
docker compose up -d db minio
docker compose run --rm minio-init
docker compose run --rm --build --no-deps migrate alembic upgrade 0008
docker compose run --rm --no-deps migrate python -m northstar.storage_admin export-legacy
docker compose run --rm --no-deps migrate alembic upgrade head
docker compose up -d backend worker
```

The exporter uploads each original, reads it back and verifies SHA-256 before saving
its key. It can resume after interruption. Migration 0009 refuses unexported rows,
then removes `original` and requires `storage_key`. Existing versions become UNCLASSIFIED
and PENDING_REVIEW; old index snapshots are purged. Use the classification endpoint
(`/documents/{id}/classification`, title/sensitivity/reason) before review and approval.
Downgrade with documents is intentionally blocked: restore a coordinated pre-migration
backup instead of inventing empty originals. Migration does not contact a model.

Uploads reserve keys before writing objects. If storage succeeds but DB commit fails,
the unreferenced key remains inspectable. With writers stopped, preview cleanup:

```powershell
docker compose run --rm --no-deps migrate python -m northstar.storage_admin cleanup
docker compose run --rm --no-deps migrate python -m northstar.storage_admin cleanup --apply
```

Only unreferenced reservations older than 24 hours are eligible; document originals,
including retained deleted records, are protected. No destructive bucket-wide scan is used.

## Cloud storage

Use the same S3 adapter, a private bucket, HTTPS, least-privilege service credentials
(or the SDK IAM role chain), public-access blocking, encryption at rest and private
network access where required. Configure `STORAGE__BUCKET`, `REGION`, optional `ENDPOINT`,
`ENCRYPTION=aws:kms` and `KMS_KEY_ID`. Do not use development MinIO root credentials.
Application and backup service permissions must cover the relevant sensitivity levels.
Storage-key references assume a stable bucket; migrating buckets requires copying and
verifying all referenced objects before switching configuration. The backup/restore
procedure must cover both PostgreSQL and the object bucket, with matching access rules.

## Evaluation, not intuition

`python -m northstar.evaluation.document_review` calls the same classifier and routing
policy as the worker. The starter file has **12 synthetic draft-labeled examples**,
including clean, incomplete, conflicting, ambiguous and injection-containing documents.
They are not a manually verified benchmark and do not establish production reliability.
Have domain reviewers validate labels and expand to 50–100 representative permitted
examples, including intentional policy changes and extraction failures. Keep a held-out
set separate from prompt development, record disagreements and compare providers on
the same set and prompt version.

From `backend`:

```powershell
../.venv/Scripts/python.exe -m northstar.evaluation.document_review tests/fixtures/document_review_draft.jsonl --dry-run --output ../evaluation-results/dataset-check.json
# After manual labels are verified, with the provider configured:
../.venv/Scripts/python.exe -m northstar.evaluation.document_review path/to/reviewed.jsonl --output ../evaluation-results/ollama.json
```

Exploratory runs on draft labels require `--allow-draft-labels`. Run each provider
separately using its settings. The report contains recall/precision on completed calls,
false negatives, false positives, coverage, schema/evidence validity, failures, unavailable
counts, latency p50/p95 and usage. It never treats failed calls routed to humans as
perfect classifier recall. Token cost is null unless actual token counts and explicit
`--input-usd-per-million` / `--output-usd-per-million` rates are supplied; local hardware
cost is separate. Report files omit passages, quotations and model explanations.

Prioritize false negatives while monitoring reviewer workload. Set acceptance thresholds
with stakeholders after a baseline; no universal threshold is claimed. Fine-tuning is
deferred until representative labels demonstrate a persistent problem. No live-model
results are included in the repository merely because contract tests pass.

## Official references

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Ollama Docker](https://docs.ollama.com/docker)
- [Ollama thinking controls](https://docs.ollama.com/capabilities/thinking)
- [Ollama local-only configuration](https://docs.ollama.com/faq)
- [Qwen3 model tags](https://ollama.com/library/qwen3/tags)
- [S3 object API](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)
