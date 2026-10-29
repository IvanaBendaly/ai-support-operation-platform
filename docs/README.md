# Documentation index

```text
docs/
├── guides/          how to set up, configure, use and verify the app
├── architecture/    how each component is designed, and why
├── project/         the implementation contract, status tracker and test traceability
├── assets/          screenshots and GIFs used in the docs
├── examples/        captured demo output (JSON)
└── policies/        a sample policy document
```

## Guides

| Document | Read it to… |
| --- | --- |
| [SETUP.md](guides/SETUP.md) | Install the requirements, set up the AI, run with or without Docker, troubleshoot |
| [CONFIGURATION.md](guides/CONFIGURATION.md) | Look up any `NORTHSTAR_*` setting, including LlamaExtract and AI review |
| [USAGE.md](guides/USAGE.md) | Take a document from upload to search in the UI or through the API; evaluate the classifier |
| [VERIFICATION.md](guides/VERIFICATION.md) | Run the PostgreSQL and Compose verification steps |

## Architecture

| Document | Covers |
| --- | --- |
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | System overview and component boundaries |
| [EXTRACTION_VERIFICATION.md](architecture/EXTRACTION_VERIFICATION.md) | BR-01: parsing, quality checks, LiteParse, DPP subset, LlamaExtract, human verification |
| [DOCUMENT_REVIEW.md](architecture/DOCUMENT_REVIEW.md) | Private storage, AI review, sensitivity routing, migration, classifier evaluation |
| [KNOWLEDGE.md](architecture/KNOWLEDGE.md) | Policy and version model, ingestion and lifecycle |
| [RETRIEVAL.md](architecture/RETRIEVAL.md) | Semantic + keyword search and evidence selection |
| [KNOWLEDGE_FRONTEND.md](architecture/KNOWLEDGE_FRONTEND.md) | Admin UI screens and their limits |
| [CASES.md](architecture/CASES.md) | Support-case API and case lifecycle |
| [BUSINESS_RULES.md](architecture/BUSINESS_RULES.md) | Simulated billing domain: refunds, plans, invoices |
| [DECISIONS.md](architecture/DECISIONS.md) | Recorded implementation decisions |

## Project

| Document | Covers |
| --- | --- |
| [IMPLEMENTATION_STATUS.md](project/IMPLEMENTATION_STATUS.md) | What each feature has completed and verified, with evidence |
| [TRACEABILITY.md](project/TRACEABILITY.md) | Which tests cover which requirement |
| [IMPLEMENTATION_CONTRACT.md](project/IMPLEMENTATION_CONTRACT.md) | The original full specification |

## Writing docs

- Use fenced code blocks with a language (` ```powershell `, ` ```python `, ` ```text ` for diagrams and trees).
- Draw diagrams in Mermaid (` ```mermaid `); GitHub renders it.
- Put images in `assets/` and link them with relative paths.
- Link with relative paths, so links work on GitHub and in editors.
