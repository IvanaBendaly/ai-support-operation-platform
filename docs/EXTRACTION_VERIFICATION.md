# Document extraction and verification (BR-01, Architecture B)

Every upload passes through extraction verification before the content classifier
([DOCUMENT_REVIEW.md](DOCUMENT_REVIEW.md)) may see it, and before any human may approve
publication. Verified extraction is **not** publication: the two decisions are separate.

```text
upload ─► B1 extract ─► B2 quality ─┬─ ACCEPTABLE ───────────────► B4 DPP subset ─┐
                                    └─ UNCERTAIN/FAILED + PDF ─► B3 LiteParse ─┘  │
                         B5 fields (optional, policy-gated) ◄────────────────────┤
                                                                                  ▼
            VERIFIED ◄─ all automated checks pass       HUMAN_REQUIRED ─► B6 human decision
                │                                                              │
                └──────────► B7 append-only ExtractionRecord ◄─────────────────┘
                                         │
                       content classifier ─► human publication decision
```

## Code map

| Stage | Code | Notes |
| --- | --- | --- |
| B1 | `retrieval/extraction.py` `extract(…, diagnostics)` | Docling for PDF/DOCX; native UTF-8 for TXT/MD. Elements carry kind, page, heading, order, provenance. |
| B2 | `retrieval/verification.py` `quality()` | Non-empty, replacement characters, minimum length, page coverage, parser warnings, Docling `ConfidenceReport` scores. |
| B3 | `verification.py` `liteparse()`, `pipeline()` | Local LiteParse, OCR off, no URL input, no cloud fallback. PDFs only, only when B2 is not ACCEPTABLE. |
| B4 | `verification.py` `dpp()` | `northstar-dpp-subset-v1`; see below. |
| B5 | `retrieval/fields.py` | LlamaExtract v2 with citations and confidence. Off unless a schema, credentials and a classification allowance are configured. |
| B6 | `retrieval/extraction_review.py` `verify()`; `POST /api/admin/documents/{id}/verification`; `frontend/src/knowledge/ExtractionVerification.tsx` | ACCEPT, CORRECT, REJECT, REPROCESS; reason and current revision required. |
| B7 | `ExtractionRecord` (`knowledge_extraction_records`, migration `0010`) | One immutable row per revision: attempts, selected parser and version, quality, DPP, field assessment, corrections, actor, reason. |

The worker (`retrieval/worker.py`) runs B1–B5 inside a bounded subprocess and commits
the record, sections and status in one transaction. The synchronous fixture path in
`service.py` runs B1–B4 only.

## Outcomes

- **B2 outcome**: `ACCEPTABLE`, `UNCERTAIN` (any check not PASS) or `FAILED` (no text,
  or over the size limit).
- **B3 selection**: a fallback replaces the first attempt only when it is ACCEPTABLE,
  or when the first attempt produced nothing and the fallback is not FAILED (selected
  as a candidate for human inspection, not as accepted). Both attempts are stored.
- **Document status**: `VERIFIED` only when the selected attempt is ACCEPTABLE, the DPP
  subset needs no human, and B5 is skipped or passes. Otherwise `HUMAN_REQUIRED`.
  After a human decision: `VERIFIED`, `REJECTED` or `PENDING` (reprocessing queued).

Missing diagnostics never pass. A missing, NaN or unfloored Docling score is
`NOT_EVALUATED`, which makes B2 `UNCERTAIN`. **Consequence today:** Docling reports NaN
for OCR when OCR is disabled, and no `confidence_floor` is configured by default, so
every Docling PDF is UNCERTAIN, goes to LiteParse, and then to a human. DPP visual
rules also always require a human for PDF/DOCX. Only native TXT/MD that pass the
deterministic checks verify automatically. Relaxing this (for example treating a
not-applicable score differently) needs evaluated examples, not an assumed cutoff.

## DPP subset (B4)

The DPP is a specification, not a scoring engine. Rules implemented, each reported as
PASS, FAIL or NOT_EVALUATED with the element source:

| Rule | Check | DPP reference |
| --- | --- | --- |
| `order_sequence` | Element order is contiguous | internal only; §5.9 visual order is separate |
| `source_references` | Every element keeps a source reference | §2.3 traceability |
| `heading_content` | Headings keep their text | §4.5 (hierarchy needs a human) |
| `list_content` | List items keep their text | §8.1 (nesting needs a human) |
| `table_shape` | Rows have equal width, or Docling cells exist | §9.4.2 (spans/headers need a human) |
| `visual_reading_order` | always NOT_EVALUATED for PDF/DOCX | §5.9 |
| `forms_and_visual_fidelity` | always NOT_EVALUATED for PDF/DOCX | §10 |

A future local multimodal judge could recommend outcomes for the visual rules. It must
not replace the human decision or relax confidentiality routing.

## Field-level confidence (B5)

- Applies to configured flat scalar fields only; nested schemas fail closed.
- A field passes only with a value, at least one citation with a page and matching
  text, a finite score in [0, 1], and an evaluated `field_confidence_floor`.
- It is **never** a whole-document accuracy score.
- External calls are allowed per level by `NORTHSTAR_EXTRACTION__EXTERNAL_*` flags.
  `HIGHLY_RESTRICTED`, `UNCLASSIFIED` and unknown levels are never sent, regardless of
  flags. When a schema is configured but the document may not be sent, the record says
  `external_processing_prohibited` and the document goes to a human.
- No redirects, no proxy environment, bounded responses and a 45 s deadline. Remote
  error bodies are discarded because they may contain document text.

## Security and reliability

- Classification is checked before any external call (B5); B1–B4 are local.
- Restricted and Confidential verification requires the operator's
  `NORTHSTAR_STORAGE__RESTRICTED_ENVIRONMENT_APPROVED` attestation.
- Reprocessing re-reads the immutable original from object storage. Earlier
  `ExtractionRecord` revisions are never updated, and downgrading migration `0010`
  refuses to drop them.
- Any verification decision resets publication to `PENDING_REVIEW` and fences an
  in-flight classifier. Re-verifying published content withdraws it from retrieval
  and purges the cached index.
- `KnowledgeService.decide("APPROVED")` refuses anything not `VERIFIED`; the content
  classifier only claims `VERIFIED` documents.

## Configuration

See `.env.example` (`NORTHSTAR_EXTRACTION__*`). Compose forwards the switches that
have safe defaults; floors, field schema and LlamaExtract credentials belong in a
private override file once evaluated.

## Acceptance criteria evidence

Tests: `backend/tests/test_extraction_verification.py`, plus the gating assertions in
`test_document_review.py` and `frontend/src/knowledge/ExtractionVerification.test.tsx`.

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Primary parser per type | native text verified; Docling DOCX/PDF tests in `test_extraction_worker.py` / `test_knowledge.py` |
| 2 | Quality checks detect problems | short, replacement-character, low/missing confidence, page-gap tests |
| 3 | Selective LiteParse | not run for acceptable or non-PDF input, or when disabled; history kept; real LiteParse PDF read |
| 4 | Structural rules recorded | DPP rule outcomes; `dpp` stored in each record |
| 5 | Field confidence only where configured | skipped without schema; grounding/floor/type cases; wire contract via mock transport |
| 6 | Uncertain → human | HUMAN_REQUIRED path; UI highlights flagged passages |
| 7 | Persisted with provenance | parser version, attempts, corrections, actor, reason; earlier revisions kept |
| 8 | Highly Restricted stays local | classification matrix; isolated worker run with HIGHLY_RESTRICTED makes no call |
| 9 | No publication bypass | approval refused for rejected/unverified; classifier skips unverified |

**Not verified here:** LlamaExtract against the live API (no credentials; mocked wire
contract only), any confidence floor (no evaluated examples), and PostgreSQL/MinIO runs.
