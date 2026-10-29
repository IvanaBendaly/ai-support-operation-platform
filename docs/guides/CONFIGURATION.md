# Configuration reference

All settings are environment variables prefixed `NORTHSTAR_`. Nested groups use a
double underscore, for example `NORTHSTAR_EXTRACTION__MINIMUM_CHARACTERS`. They are
defined in [config.py](../../backend/northstar/config.py), with examples in
[.env.example](../../.env.example). Put real values in the git-ignored `.env`; never
commit keys.

## Core

| Variable | Default | Meaning |
| --- | --- | --- |
| `NORTHSTAR_ENVIRONMENT` | `development` | `development`, `test` or `production`. SQLite and folder storage are allowed only in `test` |
| `NORTHSTAR_DATABASE_URL` | required | `postgresql+psycopg://…` (or `sqlite+pysqlite://…` in test) |
| `NORTHSTAR_ALLOWED_ORIGINS` | `["http://localhost:5173"]` | CORS origins, as a JSON list |
| `NORTHSTAR_ADMIN_TOKEN` | unset | Administrator bearer token, at least 32 characters. Unset means the admin API returns 503 |
| `NORTHSTAR_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

## Object storage (`NORTHSTAR_STORAGE__*`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BACKEND` | `s3` | `s3`; `filesystem` is test-only |
| `ENDPOINT` | unset | S3-compatible endpoint (MinIO locally). Production requires HTTPS |
| `BUCKET` / `REGION` | `northstar-originals` / `us-east-1` | Bucket and region |
| `ACCESS_KEY` / `SECRET_KEY` | unset | Credentials. Locally, keep `SECRET_KEY` equal to `MINIO_ROOT_PASSWORD` |
| `ENCRYPTION` / `KMS_KEY_ID` | unset | `AES256` or `aws:kms` server-side encryption |
| `RESTRICTED_ENVIRONMENT_APPROVED` | `false` | Operator attestation required to upload or verify Confidential and Highly Restricted documents |

## Extraction verification and LlamaExtract (`NORTHSTAR_EXTRACTION__*`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `LITEPARSE_ENABLED` | `true` | Try LiteParse when a PDF's Docling result is not ACCEPTABLE |
| `MINIMUM_CHARACTERS` | `80` | Shorter extractions are UNCERTAIN and go to a human |
| `CONFIDENCE_FLOOR` | unset | Docling score floor. **Unset means a score never counts as a pass**; set it only after evaluating real examples |
| `FIELD_SCHEMA` | unset | JSON schema of the fields for LlamaExtract. Unset means LlamaExtract is skipped |
| `FIELD_CONFIDENCE_FLOOR` | unset | Minimum field confidence. Unset means every field needs a human |
| `LLAMAEXTRACT_API_KEY` / `LLAMAEXTRACT_PROJECT_ID` | unset | LlamaCloud credentials |
| `EXTERNAL_PUBLIC_ALLOWED` / `EXTERNAL_INTERNAL_ALLOWED` / `EXTERNAL_CONFIDENTIAL_EXCEPTION` | `false` | Which sensitivity levels may be sent to LlamaExtract |

**LlamaExtract** runs only when a schema, a key, a project ID **and** an allowance for
the document's sensitivity level are all set. Highly Restricted, unclassified and
unknown levels are never sent.

- **Calls:** [fields.py](../../backend/northstar/retrieval/fields.py) (`https://api.cloud.llamaindex.ai`, extract API v2).
- **Where it runs:** the worker's isolated `--extract` subprocess.
- **Compose:** only the safe defaults are forwarded. Put the rest in a private, git-ignored `compose.override.yaml`:

```yaml
services:
  worker:
    environment:
      NORTHSTAR_EXTRACTION__FIELD_SCHEMA: '{"type":"object","properties":{"policy_id":{"type":"string"},"effective_date":{"type":"string"}}}'
      NORTHSTAR_EXTRACTION__FIELD_CONFIDENCE_FLOOR: "0.9"
      NORTHSTAR_EXTRACTION__LLAMAEXTRACT_API_KEY: ${LLAMAEXTRACT_API_KEY}
      NORTHSTAR_EXTRACTION__LLAMAEXTRACT_PROJECT_ID: ${LLAMAEXTRACT_PROJECT_ID}
      NORTHSTAR_EXTRACTION__EXTERNAL_PUBLIC_ALLOWED: "true"
```

Put `LLAMAEXTRACT_API_KEY` and `LLAMAEXTRACT_PROJECT_ID` in `.env`. For a host-run
worker, set the same variables in its shell. The floor `0.9` is only an example; choose
it from evaluated examples. Only flat fields (string, number, integer, boolean) are
supported, and the confidence covers those fields only, never the whole document.
Design details: [EXTRACTION_VERIFICATION.md](../architecture/EXTRACTION_VERIFICATION.md).

## AI document review (`NORTHSTAR_REVIEW__*`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `PROVIDER` | `disabled` | `disabled`, `auto`, `openai` or `ollama` |
| `OPENAI_MODEL` / `OPENAI_API_KEY` | `gpt-4o-mini` / unset | OpenAI model and key |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://127.0.0.1:11434` / `qwen3:4b` | Must be a private address and a locally installed tag |
| `LOCAL_ENVIRONMENT_APPROVED` | `false` | Allows local Ollama review |
| `RESTRICTED_LOCAL_APPROVED` | `false` | Also allows local review of Highly Restricted documents |
| `EXTERNAL_PUBLIC_ALLOWED` / `EXTERNAL_INTERNAL_ALLOWED` / `EXTERNAL_CONFIDENTIAL_EXCEPTION` | `false` | Which levels may go to OpenAI. Highly Restricted never can |
| `TIMEOUT_SECONDS` | `60` | Per-call timeout (at most 120) |
| `MAX_INPUT_CHARS` / `MAX_OUTPUT_TOKENS` | `12000` / `1500` | Input and output budgets |

Routing is decided before any text is sent. See
[DOCUMENT_REVIEW.md](../architecture/DOCUMENT_REVIEW.md).

## Retrieval (`NORTHSTAR_RETRIEVAL__*`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RESULT_LIMIT` | `5` | Maximum evidence sections returned |
| `CONTEXT_CHARS` | `8000` | Total context budget |
| `SECTION_CHARS` | `2000` | Maximum characters per section |
| `CANDIDATE_LIMIT` | `20` | Candidates considered before reranking |
| `MIN_SCORE` / `AMBIGUITY_MARGIN` | `0.22` / `0.06` | Relevance and ambiguity thresholds |

The remaining tuning options are in `RetrievalSettings`; see [RETRIEVAL.md](../architecture/RETRIEVAL.md).

## Support-workflow model gateway (reserved)

`NORTHSTAR_MODEL_PROVIDER`, `NORTHSTAR_MODEL_NAME`, `NORTHSTAR_PROVIDER_API_KEY`,
`NORTHSTAR_MODEL_TIMEOUT_SECONDS` and `NORTHSTAR_MODEL_MAX_OUTPUT_TOKENS` configure the
future support-workflow model. They are separate from document review and unused today.
