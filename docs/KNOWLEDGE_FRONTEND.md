> C/D update: see [DOCUMENT_REVIEW.md](DOCUMENT_REVIEW.md) for the current private-object
> storage, sensitivity routing, review worker, human publication gate and connected
> Stored documents screen. Only APPROVED PUBLIC versions enter the existing LSA index;
> pgvector remains deferred. Earlier descriptions below are historical where they differ.

# Knowledge admin frontend

The frontend phase implements the new administration experience in React/TypeScript.
Run `pnpm dev` from `frontend` using Node 24+, then open http://127.0.0.1:5173.

## Scope and preview boundary

The application starts with an empty session. **Load examples** explicitly adds
illustrative records. Browser refresh discards all documents and lifecycle actions.
No original files, credentials, or extracted content are persisted to browser storage
or uploaded. The existing live readiness check is available under System status.

The backend now supports Docling PDF/DOCX extraction and a durable worker queue.
It publishes successful effective revisions automatically and uses `policy_id` for
logical identity and revision `id` for a version. This preview's review/approval
workflow and identifiers are not yet integrated with that API. The preview does
not call mutation endpoints and is not a production admin security boundary.
Authentication, permissions, authoritative inspection, job processing and persistent
retrieval eligibility remain server responsibilities.

## Implemented flows

- Library search, status filters, counts, empty states and responsive layout.
- Single and batch selection/drop; PDF/DOCX/MD/TXT extension checks, 5 MiB per file,
  10 files and 10 MiB per batch, title validation, and per-entry preparation results.
- SHA-256 of real file bytes; UTF-8 TXT/MD normalization and a second text fingerprint.
  Duplicate matches are reported without silently linking logical documents.
- Explicit new-document versus replacement selection. Stable `document_id`, unique
  `version_id`, revision numbers and version history. A pending replacement does not
  deactivate an already-published version.
- TXT/MD browser previews retain normalized line references and character ranges.
  Normalization preserves leading indentation, case, punctuation, numbers and negation;
  it only normalizes Unicode/newlines and removes trailing line whitespace.
- PDF/DOCX remain **Awaiting worker**. Their contents are neither parsed nor validated
  as genuine PDF/DOCX files by the browser. The backend worker now provides Docling extraction and source references, but
  this preview is not connected to it. No AI classification or embeddings are simulated.
- Review queue, confirmable preview approval/publication, rejection with reason,
  deactivation, whole-document deletion and a session activity list. Publication
  supersedes an existing published revision; deactivation never revives old revisions.

`src/knowledge/model.ts` holds the domain types and session preparation/lifecycle
functions. `Upload.tsx` owns the upload workflow; `App.tsx` composes library, inspector,
review and activity views. `Readiness.tsx` retains the existing live readiness check.
Replace the session adapter with authenticated API calls after the backend contract
is implemented. Server responses must supply authoritative fingerprints, extraction
jobs, source references, review decisions and eligibility. Never trust browser state
as authorization or publication evidence.

## Verification

`pnpm test` covers validation, fingerprints, explicit relationships, partial batches,
publication transitions and UI flows, plus the preserved readiness tests.
`pnpm build` performs strict TypeScript checks and produces the Vite build.
The local UI was also exercised in headless Edge at desktop and mobile viewport sizes,
including a real browser File upload and review/publication confirmation.
