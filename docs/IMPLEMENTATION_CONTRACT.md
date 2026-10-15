# MASTER CODEX IMPLEMENTATION PROMPT
## Enterprise AI Support Operations Platform
### Full Production-Minded Implementation Contract

You are acting as the principal AI engineer, senior backend engineer, software architect, QA engineer, and technical lead responsible for implementing a complete portfolio-grade software product.

Your task is to design, implement, integrate, test, evaluate, document, and deliver the following project:

**Enterprise AI Support Operations Platform**

This is not a tutorial, proof of concept, superficial LLM wrapper, or collection of isolated demos.

It must become a functional AI-powered support operations system with actual business state, policy retrieval, controlled actions, human escalation, observability, automated tests, and a reproducible model comparison benchmark.

Your implementation must prioritize:

1. Correctness and reliability.
2. Meaningful AI and software engineering depth.
3. Clear, maintainable architecture.
4. Strong portfolio demonstration value.
5. Reproducible evaluation.
6. Practical implementation speed.
7. A polished and coherent user experience.
8. Real functionality rather than hardcoded or simulated success.

The application must be realistic enough to demonstrate serious engineering ability but simple enough to be maintained by one developer.

---

# PART 1 — YOUR RESPONSIBILITIES

You are responsible for implementation from beginning to end.

Do not simply describe how features could be implemented.

Write the actual application code, tests, database migrations, configuration, scripts, documentation, and relevant frontend components.

For every feature:

- Inspect the current repository.
- Identify existing components and interfaces.
- Design the feature's internal implementation.
- Implement the complete required functionality.
- Integrate it with previous features.
- Add necessary tests.
- Execute available tests.
- Correct discovered issues.
- Update documentation.
- Verify its Definition of Done.
- Record remaining limitations accurately.

Do not claim to have tested or verified functionality unless it was actually executed.

If an external service, credential, or unavailable environment prevents verification, distinguish clearly between:

- Implemented and tested.
- Implemented but not integration-tested.
- Blocked by an external dependency.
- Not implemented.

Never present an untested feature as fully operational.

## Operating rules

### Rule 1 — Follow the complete project scope

Implement all 16 Core features described below.

Do not omit requirements simply because they are difficult.

Do not replace functional implementations with TODO comments, placeholder APIs, fabricated outputs, or mocked production logic.

Mocks are permitted in automated tests and explicitly labeled demonstrations, not as a substitute for the actual application.

### Rule 2 — Use phased implementation

Implement features in dependency order.

Do not attempt to write the entire application in one huge code generation step.

Each feature is a substantial implementation unit. Internally decompose it into smaller engineering steps as necessary.

Finish and verify a feature before treating it as complete.

Continue to subsequent features when the execution environment permits. If interrupted, save sufficient repository progress for the next session to resume accurately.

### Rule 3 — Preserve completed functionality

Every new feature must integrate with previously implemented functionality.

Do not unnecessarily rewrite stable modules.

Do not introduce breaking API contracts without updating all dependent components and tests.

Run appropriate regression tests after each substantial change.

### Rule 4 — Do not overengineer

Do not introduce Kubernetes, microservices, Kafka, complex distributed infrastructure, elaborate agent frameworks, or excessive abstraction unless a concrete Core requirement genuinely needs them.

Use straightforward, production-minded engineering.

One well-organized backend application is preferable to multiple unnecessary services.

### Rule 5 — Respect feature priorities

CORE requirements are mandatory.

STRONG PORTFOLIO additions are optional candidates and must not be implemented automatically.

OPTIONAL / LATER features must not be implemented.

If a Strong Addition appears beneficial, record it as a recommendation rather than adding it silently.

### Rule 6 — Make engineering decisions explicit

When the specification leaves a decision open:

1. Choose the simplest robust approach.
2. Favor established, maintainable tools.
3. Prefer solutions that are easy to test.
4. Keep dependencies limited.
5. Document material tradeoffs.
6. Avoid creating unnecessary extension points.

Do not interrupt implementation for minor choices.

Ask for input only when an essential credential, destructive action, significant cost, or materially different product requirement makes proceeding unsafe.

### Rule 7 — Never conceal failures

If a model, tool, database operation, or evaluation fails, preserve the correct error state.

Never fabricate successful actions or benchmark results.

Never silently substitute fake data for real model evaluations.

### Rule 8 — Optimize for a real portfolio reviewer

A technical interviewer should be able to:

- Understand the architecture.
- Start the application.
- Inspect source code.
- Follow request execution.
- Verify important business invariants.
- Inspect model interactions.
- Read evaluation methodology.
- Reproduce representative results.
- Understand why specific engineering choices were made.

Every important portfolio claim must have evidence.

---

# PART 2 — PRODUCT DEFINITION

## Business scenario

Build the platform for a fictional SaaS company named **Northstar Cloud**.

Northstar Cloud offers subscription-based software services.

Its customers contact support regarding:

- Product features and policies.
- Account and subscription information.
- Billing and invoices.
- Subscription plan changes.
- Refund eligibility.
- Account-related questions.
- Requests requiring clarification.
- Requests requiring human approval.
- Unsupported or prohibited operations.

The platform must support the full lifecycle of these requests.

## Intended users

### Customer

A customer can:

- Authenticate.
- Submit a support request.
- View their support cases.
- Continue a conversation.
- Receive AI-generated policy-grounded answers.
- Request permitted business actions.
- Receive clarification requests.
- See when a case has been escalated.
- View final case outcomes.

A customer cannot inspect or modify another customer's private information.

### Support operator

An operator can:

- Authenticate.
- View relevant support cases.
- Inspect case history.
- Review escalated cases.
- Inspect supporting policy evidence.
- Inspect proposed actions.
- Approve an eligible action where permitted.
- Reject proposed actions.
- Request clarification.
- Resolve cases manually.
- Inspect operational action history.

### Administrator

For this project's practical scope, an authorized operator may also have administrative permissions to:

- Upload and manage policies.
- Inspect ingestion failures.
- Run evaluations.
- View benchmark reports.
- Inspect diagnostic traces.

Implement clear authorization boundaries.

A complex enterprise role-management application is not required.

---

# PART 3 — REQUIRED TECHNOLOGY STACK

Use a coherent, modern, maintainable stack.

Default choices:

## Backend

- Python 3.12 or newer compatible version.
- FastAPI.
- Pydantic v2.
- SQLAlchemy 2.x.
- Alembic.
- PostgreSQL.
- PostgreSQL vector search using pgvector when appropriate.

## Frontend

- React.
- TypeScript.
- Vite.
- A lightweight, consistent component styling approach.

Tailwind CSS is acceptable if it simplifies implementation.

Avoid large unnecessary frontend dependencies.

## AI

- An LLM provider abstraction with at least one real provider implementation.
- Structured model outputs where supported.
- Versioned prompt definitions.
- Provider usage and latency recording.
- A deterministic fake/mock model implementation for tests.

Prefer direct provider SDK integration over introducing a large agent framework unless it materially simplifies the project.

## Retrieval

- Document extraction.
- Text chunking.
- Embeddings.
- Vector similarity search.
- Source metadata and citation tracking.

## Testing

- pytest.
- FastAPI integration tests.
- Database integration tests.
- Mocked LLM tests.
- Deterministic test fixtures.
- Basic frontend tests for critical interactions.
- GitHub Actions for automated checks.

## Runtime

- Docker and Docker Compose for reproducible local execution.
- Environment-based configuration.
- Structured logging.

## Engineering guidance

Before using major dependencies, check their current stable documentation and compatibility.

Avoid deprecated interfaces.

Pin or constrain dependency versions appropriately.

Do not introduce technology simply for resume keywords.

---

# PART 4 — SYSTEM ARCHITECTURE

The intended logical flow is:

Customer or operator

→ Frontend

→ FastAPI backend

→ Authentication and authorization

→ Support case lifecycle

→ AI decision workflow

→ Business context + policy retrieval

→ Structured model decision

→ Decision validation

→ Safe action execution / answer / clarification / escalation

→ Verified response

→ Persistent case outcome

Throughout processing:

- Structured logs.
- Correlated traces.
- Action audit records.
- Model usage data.
- Errors and failure classifications.

Separately:

Evaluation dataset

→ Evaluation runner

→ Same production-path support workflow

→ Isolated business fixtures

→ Outcome graders

→ Configuration comparisons

→ Benchmark report.

## Architectural principles

### Separation of concerns

Separate:

- API request handling.
- Business domain logic.
- Database access.
- AI provider communication.
- Retrieval.
- Workflow orchestration.
- Tool execution.
- Response validation.
- Human review.
- Evaluation.
- Observability.

### Business operations must not be controlled solely by the LLM

The model may suggest an action.

Only trusted backend code may authorize and execute it.

### Database records are authoritative

A generated text response does not prove that a business action occurred.

Only confirmed persisted business outcomes establish completion.

### Every consequential action should be traceable

Persist sufficient context to explain what was proposed, validated, executed, and communicated.

### Evaluation must reuse real application behavior

Do not implement a separate simplified algorithm for the benchmark.

Benchmark cases must pass through the same core workflow as ordinary support cases.

### Reproducibility matters

Control:

- Business fixtures.
- Policy corpus versions.
- Evaluation dataset versions.
- Model configuration.
- Prompt configuration.
- Grading rules.

---

# PART 5 — IMPLEMENTATION PROCESS

Follow the feature order below.

Before writing significant code, create:

1. A concise architecture document.
2. A repository structure.
3. A feature implementation tracker.
4. An implementation decision log.
5. A requirements-to-tests traceability document.

These are working project documents, not lengthy theoretical reports.

Create an `IMPLEMENTATION_STATUS.md` file containing every feature, its status, completed acceptance criteria, blockers, and relevant test commands.

Feature states:

- NOT_STARTED
- IN_PROGRESS
- IMPLEMENTED_UNVERIFIED
- VERIFIED
- BLOCKED

Update this file throughout development.

A feature must not be marked VERIFIED unless its mandatory Definition of Done passes.

## Standard feature delivery cycle

For each feature:

**Step 1 — Inspect**

Review related modules, data models, contracts, and tests.

**Step 2 — Design**

Identify the feature's interfaces, data changes, failure handling, and required integration points.

**Step 3 — Implement**

Write the actual functionality, including database changes and API contracts where applicable.

**Step 4 — Test**

Add unit, integration, or end-to-end tests appropriate to the feature.

**Step 5 — Integrate**

Check compatibility with the existing application.

**Step 6 — Validate**

Execute appropriate commands and inspect outcomes.

**Step 7 — Document**

Update API documentation, architecture, decisions, or operating instructions where necessary.

**Step 8 — Complete**

Check every mandatory Definition of Done item and update the implementation tracker.

Do not convert Strong Additions into mandatory work.

---

# PART 6 — CORE IMPLEMENTATION FEATURES

## FEATURE C01 — PROJECT FOUNDATION AND CONFIGURATION

### Purpose

Create the engineering foundation for the application.

### Must build

1. Backend application with clearly organized modules.
2. Frontend application shell.
3. PostgreSQL connection.
4. SQLAlchemy models and session management foundation.
5. Alembic migration setup.
6. Environment-based configuration.
7. Configuration validation.
8. Health and readiness endpoints.
9. Standard error responses.
10. Request validation conventions.
11. Structured logging foundation.
12. Unit/integration test infrastructure.
13. Formatting and linting configuration.
14. Docker Compose local environment.
15. Development startup documentation.

### Expected behavior

- A fresh checkout can be configured and started.
- Application initialization validates configuration.
- Database schema migrations execute correctly.
- The backend communicates with the frontend.
- Missing configuration produces meaningful failures.
- Readiness correctly reflects important dependencies.

### Failure handling

Handle:

- Missing environment variables.
- Invalid configuration values.
- Database connection failures.
- Migration failures.
- Incomplete startup.

### Definition of Done

- Backend starts successfully.
- Frontend starts successfully.
- Database connects.
- Migrations work from an empty database.
- Health/readiness endpoints function correctly.
- Foundational tests pass.
- Startup instructions are documented.
- No secrets are committed.

---

## FEATURE C02 — BUSINESS DOMAIN AND DATABASE

### Purpose

Create a realistic simulated SaaS business backend.

### Must build

Persistent entities for:

- Customers.
- Accounts.
- Subscription plans.
- Subscriptions.
- Invoices.
- Refunds.

Model:

- Valid subscription states.
- Plan information.
- Subscription dates.
- Invoice amounts and currencies.
- Payment status.
- Refund history.
- Refund limits.
- Business record ownership.
- Valid business state transitions.

Provide internal business services for:

- Account retrieval.
- Subscription retrieval.
- Invoice retrieval.
- Subscription updates.
- Refund operations.

Enforce business invariants in trusted domain logic.

Do not rely on the AI model to enforce them.

Provide deterministic database seed data.

Include scenarios for:

- Active subscriptions.
- Canceled subscriptions.
- Paid invoices.
- Unpaid invoices.
- Eligible refunds.
- Ineligible refunds.
- Previously refunded invoices.
- Different plans.
- Missing records.
- Conflicting account states.

Provide a reliable way to reset the business environment for tests and evaluations.

### Failure handling

- Invalid foreign keys.
- Missing records.
- Invalid state transitions.
- Duplicate refunds.
- Concurrent updates.
- Partially completed database transactions.

### Definition of Done

- Every domain entity persists correctly.
- Domain relationships are valid.
- Invalid operations are rejected.
- Transaction boundaries protect consistency.
- Seed/reset is deterministic.
- Domain tests pass.

---

## FEATURE C03 — POLICY DOCUMENT INGESTION

### Purpose

Build a real policy knowledge-management ingestion pipeline.

### Must build

Support:

- Markdown.
- Plain text.
- Text-based PDF.

Provide administrative APIs for:

- Upload.
- List documents.
- Inspect document status.
- View document metadata.
- Replace an existing policy.
- Deactivate a policy.

The ingestion pipeline must:

1. Validate file type.
2. Validate file size.
3. Reject empty files.
4. Handle malformed files.
5. Extract usable text.
6. Normalize text appropriately.
7. Split content into retrievable sections.
8. Preserve source/page or section information.
9. Generate stable document and section identifiers.
10. Detect duplicate content.
11. Store original document metadata.
12. Preserve document versions.
13. Track ingestion status.
14. Record meaningful processing errors.
15. Prevent inactive policies from being used as active evidence.

Use a practical policy corpus for Northstar Cloud covering:

- Refund conditions.
- Subscription changes.
- Billing policies.
- Cancellation.
- Account eligibility.
- Support escalation requirements.
- Common product questions.

Policies should be internally consistent with implemented business rules.

### Failure handling

- Corrupt PDF.
- Unsupported file type.
- Empty extraction.
- Duplicate upload.
- Partial processing failure.
- Superseded policy remaining active.

### Definition of Done

- Supported formats ingest successfully.
- Invalid formats fail safely.
- Document sections retain citations.
- Versioning works.
- Duplicate handling works.
- Active/inactive state works.
- Processing errors are visible.
- Ingestion tests pass.

---

## FEATURE C04 — KNOWLEDGE RETRIEVAL

### Purpose

Make the company's policy documents searchable using semantic retrieval.

### Must build

- Embedding generation.
- Storage of embeddings.
- Vector similarity search.
- Reusable retrieval service.
- Configurable result count.
- Configurable retrieved-context limits.
- Source attribution.
- Active-policy filtering.
- Document version filtering.
- Index updates after document replacement.
- Index removal or invalidation after deactivation.
- Explicit no-evidence results.
- Error differentiation between no match and retrieval failure.

Return structured retrieval results containing:

- Document ID.
- Document version.
- Chunk/section ID.
- Relevant text.
- Source location.
- Ranking information.

Do not fabricate retrieved documents.

### Failure handling

- Empty results.
- Incorrect policy version.
- Embedding generation failure.
- Index inconsistency.
- Provider unavailable.
- Excessive retrieved context.

### Definition of Done

- Relevant sections are found for representative queries.
- Every result is attributable to a real policy source.
- Inactive/superseded policies are excluded.
- Updates are reflected correctly.
- Retrieval failures are observable.
- Retrieval tests pass.

---

## FEATURE C05 — SUPPORT CASE API AND LIFECYCLE

### Purpose

Create durable support cases with real conversation and processing state.

### Must build

APIs for:

- Creating cases.
- Listing authorized cases.
- Retrieving a case.
- Viewing messages.
- Adding follow-up messages.
- Inspecting case outcome/status.

Persist:

- Case ID.
- Customer/account association.
- Incoming messages.
- Assistant messages.
- Processing attempts.
- Current state.
- Final disposition.
- Relevant timestamps.
- Error information.
- Related action and escalation references.

Support case states:

- OPEN.
- PROCESSING.
- AWAITING_CUSTOMER.
- ESCALATED.
- RESOLVED.
- FAILED.

Support dispositions such as:

- ANSWERED.
- ACTION_COMPLETED.
- CLARIFICATION_REQUESTED.
- REFUSED.
- HUMAN_ESCALATION.

Implement valid state transitions.

Provide idempotency for case submission where appropriate.

Ensure interrupted processing has a recoverable or explicitly failed state.

### Failure handling

- Duplicate requests.
- Invalid state transitions.
- Unauthorized access.
- Missing customer.
- Concurrent processing.
- Interrupted processing.
- Invalid follow-up state.

### Definition of Done

- Cases persist.
- Messages persist.
- State transitions are enforced.
- Follow-ups work.
- Duplicate submissions do not create duplicate cases.
- Failures are visible.
- Access boundaries work.
- API tests pass.

---

## FEATURE C06 — MODEL GATEWAY

### Purpose

Provide a reliable interface to the AI model.

### Must build

- Provider abstraction.
- One working real LLM provider.
- Deterministic mocked provider for tests.
- Selectable model configurations.
- Versioned prompts.
- Structured output schemas.
- Response parsing.
- Schema validation.
- Timeout handling.
- Bounded retries.
- Provider error classification.
- Token usage recording.
- Latency recording.
- Estimated cost calculation.
- Provider/model identification.

Supported response decisions should include:

- ANSWER.
- CLARIFY.
- PROPOSE_ACTION.
- REFUSE.
- ESCALATE.

A model response must not be trusted simply because it is valid JSON.

Validate structured output semantically where relevant.

At least two model configurations must be supported for evaluation.

Avoid automatic retries that could duplicate business actions.

### Failure handling

- Provider timeout.
- Rate limit.
- Unavailable provider.
- Invalid schema.
- Missing fields.
- Unsupported decision.
- Truncated output.
- Missing usage metrics.

### Definition of Done

- Live provider integration operates with valid credentials.
- Structured responses are validated.
- Malformed responses fail safely.
- Usage/latency metadata is recorded.
- Prompt/model versions are tracked.
- Mocked tests work without live API access.
- Two configurations can be selected.
- Gateway tests pass.

---

## FEATURE C07 — AI SUPPORT WORKFLOW ORCHESTRATION

### Purpose

Implement the central intelligent support-processing workflow.

### Must build

For every support processing attempt:

1. Load the case.
2. Load relevant conversation history.
3. Retrieve customer/account information.
4. Retrieve relevant policy evidence.
5. Prepare bounded model context.
6. Invoke the model.
7. Validate the model's structured decision.
8. Check evidence requirements.
9. Determine the appropriate next operation.
10. Route to response, clarification, action proposal, refusal, or escalation.
11. Persist the workflow decision.
12. Preserve relevant source references.
13. Terminate within bounded execution limits.
14. Handle recoverable errors safely.

Decisions must be based on:

- User request.
- Current business data.
- Applicable policy evidence.
- Permitted operational capabilities.
- Current case context.

The model must not invent authorized actions.

The workflow must not treat prompt-injection instructions within documents or customer messages as system rules.

If information is missing, ask a meaningful clarification question.

If an action requires authorization or policy evidence that is not available, do not execute it.

If evidence conflicts, avoid unsupported automated resolution.

A bounded second retrieval attempt is NOT mandatory.

### Failure handling

- Invented operations.
- Missing evidence.
- Conflicting evidence.
- Invalid model output.
- Prompt injection.
- Endless processing.
- Partial workflow failure.
- Inconsistent case state.

### Definition of Done

- Policy answer scenario works.
- Clarification scenario works.
- Action proposal works.
- Refusal scenario works.
- Escalation scenario works.
- Unsupported operations are rejected.
- The workflow is bounded.
- Decisions are traceable.
- Workflow integration tests pass.

---

## FEATURE C08 — BUSINESS TOOL EXECUTION

### Purpose

Safely execute actual state-changing support actions against the simulated business environment.

### Must build

Registered tools:

1. Get account details.
2. Get subscription.
3. Get invoices/payment history.
4. Change subscription plan.
5. Issue an eligible refund.

For every tool:

- Define an explicit input contract.
- Validate arguments.
- Verify requester authorization.
- Validate target account ownership.
- Verify business rules.
- Verify required policy conditions.
- Execute through trusted backend services.
- Return structured outcomes.
- Record execution attempts.
- Record actual database changes.

For mutating tools:

- Use database transactions.
- Enforce idempotency.
- Handle concurrent updates.
- Prevent duplicate financial operations.
- Preserve failure states.
- Prevent direct execution from unvalidated model output.

Define executable business policy rules consistent with the policy corpus.

For refunds, validate applicable limits, invoice payment status, prior refunds, and eligibility.

For subscription changes, validate allowed plans and state transitions.

The model's recommendation is never sufficient authorization.

### Failure handling

- Unauthorized account access.
- Duplicate refund.
- Invalid invoice.
- Invalid plan.
- Ineligible action.
- Concurrent state changes.
- Database failure.
- Invalid tool parameters.

### Definition of Done

- All five tools operate.
- Read-only tools return real persisted data.
- Mutating tools change real persisted records.
- Unauthorized changes are rejected.
- Duplicate execution is prevented.
- Transactions protect consistency.
- Final outcomes reflect committed state.
- Tool safety tests pass.

---

## FEATURE C09 — GROUNDED RESPONSES AND OUTCOME VERIFICATION

### Purpose

Generate accurate customer responses grounded in real evidence and confirmed operations.

### Must build

Responses for:

- Successful policy answers.
- Successful actions.
- Refused actions.
- Clarification requests.
- Escalations.
- Failed operations.

Use:

- Verified business state.
- Valid policy evidence.
- Actual action execution results.
- Structured case dispositions.

Ensure:

- Policy citations reference existing sources.
- Incorrect citations are rejected or handled safely.
- Claimed financial amounts match actual records.
- Claimed plan changes match actual records.
- Failed actions are never described as completed.
- A response failure does not trigger duplicate action execution.
- Customer-visible responses do not disclose internal secrets.
- Generated messages are persisted.

Introduce validation sufficient to detect material contradictions between response and authoritative outcome.

Avoid claiming that citation existence alone proves every semantic claim correct.

### Failure handling

- Hallucinated citation.
- Wrong amount.
- Incorrect subscription plan.
- False success statement.
- Missing source evidence.
- Model generation failure after successful execution.

### Definition of Done

- Every disposition produces a suitable response.
- Policy sources are valid.
- Action success claims match committed outcomes.
- Material mismatches are rejected.
- Safe fallback messages work.
- Messages and citations persist.
- Response consistency tests pass.

---

## FEATURE C10 — HUMAN ESCALATION AND REVIEW

### Purpose

Support actual human intervention for cases that cannot safely be automated.

### Must build

Escalation records with:

- Case ID.
- Escalation reason.
- Relevant customer request.
- Policy evidence.
- Relevant business state.
- Proposed action where applicable.
- Decision context.
- Review status.
- Reviewer identity.
- Review decision.
- Timestamps.

Support reasons including:

- Insufficient evidence.
- Conflicting policy.
- Unauthorized action.
- Unsupported request.
- Ambiguous case.
- Action failure.
- Required human judgment.

Provide operator APIs for:

- Listing pending reviews.
- Inspecting a review.
- Rejecting an action.
- Approving an eligible pending action.
- Requesting clarification.
- Resolving a case manually.

Operator-approved actions must still pass business authorization and eligibility validation.

Prevent duplicate review completion.

Handle conflicting simultaneous operator decisions.

### Failure handling

- Stale proposed action.
- Approval of no-longer-eligible operation.
- Two competing reviews.
- Missing review evidence.
- Unauthorized reviewer.
- Inconsistent case state.

### Definition of Done

- Cases escalate correctly.
- Review context is available.
- Operator decisions persist.
- Rejected actions do not execute.
- Approved actions pass final validation.
- Duplicate review decisions are prevented.
- Case status updates correctly.
- Human-review tests pass.

---

## FEATURE C11 — SECURITY AND SAFEGUARDS

### Purpose

Protect customer information and prevent unauthorized operations.

### Must build

- Authentication.
- Customer/operator role separation.
- Resource ownership checks.
- Case authorization.
- Account authorization.
- Administrative endpoint protection.
- Tool authorization.
- Secret management.
- Sensitive-data protection in logs.
- Input validation.
- Request size limits.
- Basic rate limiting.
- Model call budgets.
- Execution time limits.
- Safe API error messages.
- Prompt-injection defensive boundaries.

Specific safeguards:

- Customer A cannot access Customer B's cases.
- Customer A cannot change Customer B's subscription.
- Model output cannot grant permissions.
- Retrieved document text cannot override execution policy.
- Unregistered actions cannot execute.
- Business actions cannot bypass backend validation.
- Operator permissions are checked server-side.
- Evaluation and administrative operations are restricted.
- Demo data must be fictional/synthetic.

Do not build enterprise SSO or formal compliance infrastructure.

### Definition of Done

- Role and ownership checks work.
- Unauthorized requests are rejected.
- Tool boundaries are enforced.
- Prompt injection does not bypass action authorization.
- Secrets remain protected.
- Cost and execution limits work.
- Relevant security tests pass.

---

## FEATURE C12 — FRONTEND AND OPERATOR DASHBOARD

### Purpose

Create a polished, coherent interface that makes the platform genuinely usable and demonstrable.

The interface should resemble a professional SaaS support operations dashboard.

Avoid a generic AI chatbot page as the entire product.

## Design direction

Use:

- Clean layout.
- Consistent typography.
- Professional neutral color palette with restrained accent colors.
- Clear information hierarchy.
- Readable tables.
- Status indicators.
- Well-designed loading/empty/error states.
- Consistent spacing.
- Responsive layout.
- Accessible controls.
- Simple navigation.

Prefer functional clarity over decoration.

## Required application layout

### Main navigation

Provide appropriate navigation for:

- Support.
- Cases.
- Escalations.
- Knowledge Base.
- Evaluations.
- Settings or configuration information where useful.

Navigation visibility must respect user roles.

### Customer support screen

Include:

- Conversation view.
- Message submission.
- Case status.
- Policy citations.
- Action outcome.
- Clarification messages.
- Escalation status.
- Previous case history.

### Operator case management screen

Include:

- Case list.
- Case status.
- Customer/account reference.
- Latest disposition.
- Case detail.
- Conversation history.
- Evidence references.
- Tool action history where appropriate.

### Escalation review screen

Include:

- Pending review list.
- Escalation reason.
- Relevant evidence.
- Proposed action.
- Case context.
- Approve/reject controls.
- Clarification control.
- Manual resolution.
- Review outcome history.

### Knowledge administration screen

Include:

- Document upload.
- Existing document list.
- Processing status.
- Document version.
- Active/inactive status.
- Failure messages.
- Deactivation.
- Replacement where supported.

### Evaluation screen

Include:

- Available benchmark reports.
- Compared model configurations.
- Key correctness and safety metrics.
- Cost and latency results.
- Link or navigation to full report data.

Interactive benchmark visualizations are optional; readable tables and reports are sufficient for Core.

## UI behavior

- No fake buttons.
- No dead navigation.
- No fabricated metrics.
- No static success messages unrelated to actual API outcomes.
- No action completion displayed before backend confirmation.
- Handle duplicate submission.
- Handle loading.
- Handle failed requests.
- Handle empty data.
- Preserve useful state after refresh.
- Present readable validation errors.

### Definition of Done

- A customer can submit and follow a case.
- An operator can view cases.
- An operator can resolve escalations.
- Policies can be managed.
- Case outcomes display accurately.
- Benchmark summaries can be viewed.
- Authorization works.
- Main UI flows are tested.
- Main user journeys are visually reviewed for layout and usability.

---

## FEATURE C13 — OBSERVABILITY, AUDIT, DEBUGGING

### Purpose

Make every important AI and operational decision investigable.

### Must build

For each support processing attempt:

- Correlation ID.
- Case ID.
- Workflow attempt ID.
- Model call details.
- Retrieval result references.
- Decision category.
- Action proposal.
- Authorization outcome.
- Tool execution outcome.
- Escalation outcome.
- Final response disposition.
- Stage timestamps.
- Relevant duration metrics.
- Error categories.

Track model usage:

- Provider.
- Model.
- Prompt/configuration version.
- Input tokens.
- Output tokens.
- Total tokens where available.
- Estimated cost.
- Latency.

Keep a durable audit trail for:

- Business mutations.
- Authorization decisions where consequential.
- Human approvals.
- Human rejections.
- Escalation resolutions.

Separate durable audit events from optional telemetry.

Provide a way to inspect the trace for a given case or processing attempt.

Important failure categories:

- Model failure.
- Invalid model output.
- Retrieval failure.
- Missing evidence.
- Authorization failure.
- Policy conflict.
- Tool failure.
- Database failure.
- Response validation failure.
- Internal processing failure.

### Definition of Done

- A case's important execution path is traceable.
- Model calls and tools are correlated.
- Consequential actions have durable audit records.
- Known failures have meaningful classifications.
- Cost and latency measurements are available.
- Sensitive data is protected.
- Telemetry failures do not incorrectly change business outcomes.
- Representative errors can be diagnosed from recorded data.

---

## FEATURE C14 — AUTOMATED TESTING

### Purpose

Provide meaningful evidence of correctness and reliability.

### Must build

Tests for:

**Foundation**
- Configuration validation.
- Startup/readiness.
- Database migrations.

**Domain**
- Relationships.
- State transitions.
- Financial invariants.
- Transactions.
- Seed/reset.

**Ingestion**
- Supported formats.
- Invalid documents.
- Duplicate content.
- Versions.
- Deactivation.

**Retrieval**
- Relevant policy retrieval.
- Source attribution.
- Inactive-policy exclusion.
- Index updates.
- Failure handling.

**Case management**
- Case creation.
- Authorization.
- Duplicate submissions.
- Valid state transitions.
- Follow-up messages.

**Model gateway**
- Valid structured output.
- Invalid output.
- Provider errors.
- Timeouts.
- Missing usage data.

**Orchestration**
- Answer.
- Clarification.
- Action proposal.
- Refusal.
- Escalation.
- Conflicting policies.
- Unsupported tools.
- Bounded execution.

**Actions**
- Permitted actions.
- Ineligible actions.
- Unauthorized actions.
- Duplicate refunds.
- Idempotency.
- Concurrent modifications.
- Transaction consistency.

**Responses**
- Valid citations.
- Correct action status.
- Incorrect success claims.
- Fallback generation.

**Escalation**
- Review lifecycle.
- Approval.
- Rejection.
- Stale approval.
- Conflicting operator actions.

**Security**
- Cross-customer access.
- Unauthorized mutations.
- Administrative endpoint protection.
- Prompt-injection boundary protection.

**End-to-end**
- Successful policy answer.
- Valid subscription change.
- Valid refund.
- Ineligible refund.
- Missing information.
- Required escalation.
- Human resolution.
- Provider failure.

Requirements:

- Standard automated tests must work without real LLM calls.
- Use deterministic mock responses.
- Use isolated databases or resettable fixtures.
- Tests must detect actual incorrect behavior.
- No tests that merely assert mocked success regardless of implementation.

Add automated test execution through GitHub Actions.

### Definition of Done

- Critical domain invariants are tested.
- All main decision types are tested.
- Major failure paths are tested.
- End-to-end workflows pass.
- Tests are repeatable.
- Standard CI tests do not require paid model usage.
- Automated checks are configured.
- Test results are documented.

---

## FEATURE C15 — EVALUATION AND MODEL BENCHMARK

### Purpose

Build the project's main portfolio differentiator: a reproducible comparison of AI support configurations based on correctness, safety, escalation performance, latency, cost, and failure rates.

This feature must be treated as a complete evaluation engineering subsystem, not a simple results chart.

## C15.1 — Evaluation dataset

Build a versioned dataset containing at least 100 labeled scenarios.

Include:

- Simple policy questions.
- Multi-policy questions.
- Account information requests.
- Billing questions.
- Eligible refunds.
- Ineligible refunds.
- Duplicate refund attempts.
- Subscription changes.
- Invalid subscription changes.
- Missing account information.
- Missing necessary details.
- Conflicting policies.
- Ambiguous user requests.
- Unauthorized actions.
- Cases requiring escalation.
- Provider and workflow failure scenarios where applicable.

For every scenario preserve:

- Scenario ID.
- Scenario category.
- User input.
- Relevant conversation context.
- Initial business state.
- Required policy corpus/version.
- Expected decision category.
- Acceptable outcomes where necessary.
- Expected tool and arguments when applicable.
- Prohibited actions.
- Expected final business state.
- Relevant policy evidence.
- Labeling notes.
- Applicable grading rules.

Make labels explicit and reviewable.

Avoid ambiguous scenarios with no defensible expected outcome.

## C15.2 — Evaluation execution

Build an evaluation runner that:

1. Loads the versioned dataset.
2. Selects a model/workflow configuration.
3. Resets or isolates business state.
4. Executes each case using the same core application workflow.
5. Records decision outcomes.
6. Records tool proposals.
7. Records actual business mutations.
8. Records escalations.
9. Records cited evidence.
10. Records provider failures.
11. Records latency.
12. Records token usage and estimated cost.
13. Applies evaluation graders.
14. Persists per-case results.
15. Generates aggregate metrics.
16. Preserves run configuration.

Support at least two different real model configurations.

Do not fabricate real model evaluation results when credentials are unavailable.

A mocked demonstration benchmark must be clearly labeled as synthetic and must not be represented as real model performance.

## C15.3 — Metrics

Implement precisely defined metrics.

### Decision accuracy

Compare the selected decision category against the labeled expected outcome.

### Action correctness

Evaluate:

- Whether the correct operation was selected.
- Whether its arguments were correct.
- Whether execution was authorized.
- Whether persisted business state matches the expected result.

### Unauthorized action safety

Track:

- Unauthorized actions proposed.
- Unauthorized actions attempted.
- Unauthorized actions actually executed.

These are different measurements.

### Escalation precision

Among cases the system escalated, what proportion genuinely required escalation according to the labeled evaluation rules?

### Escalation recall

Among cases that required escalation, what proportion were actually escalated?

### Unsafe automation rate

Measure inappropriate automatic resolution of scenarios that should not have been automatically resolved.

### Policy grounding

Measure:

- Citation existence.
- Correct source identity.
- Relevance to expected policy.
- Unsupported statements where grading can reliably establish them.

Do not treat citation validity as full semantic grounding correctness.

### Workflow completion rate

Measure successfully completed processing, distinct from correct support resolution.

### Resolution correctness

Measure whether the final supported outcome was correct.

### Cost

Track:

- Estimated model cost per case.
- Total evaluation model cost.
- Mean/median cost.
- Costs associated with failures and retries.

### Latency

Track:

- End-to-end latency.
- Model latency.
- Retrieval latency.
- Tool latency where meaningful.
- Median latency.
- p95 latency when supported by sufficient data.

### Failure rates

Classify failures by meaningful category.

Include failed and incomplete scenarios in reporting rather than hiding them.

## C15.4 — Benchmark comparison

Compare at least two model configurations on the same scenarios.

Ensure:

- Same business starting states.
- Same active policy corpus.
- Same grading rules.
- Same scenario versions.
- Documented inference settings.
- Documented execution environment.

Produce:

- Configuration comparison table.
- Decision accuracy results.
- Action correctness results.
- Safety results.
- Escalation precision/recall.
- Latency comparison.
- Cost comparison.
- Failure rate comparison.
- Representative errors.
- Benchmark limitations.

Do not assert statistical significance without suitable evidence.

Do not choose a winning configuration solely from one headline metric.

## C15.5 — Benchmark artifacts

Generate:

- Machine-readable per-case results.
- Aggregate metric files.
- Reproducible run configuration.
- Human-readable Markdown report.
- Charts where useful.
- Metric definitions.
- Dataset documentation.
- Evaluation limitations.

Provide simple dashboard access to published reports.

## Definition of Done

- At least 100 labeled scenarios.
- Dataset versioning.
- Repeatable business fixtures.
- Real workflow evaluation.
- Two selectable real model configurations.
- Correct action-state grading.
- Safety metrics.
- Escalation precision/recall.
- Cost and latency metrics.
- Failure classification.
- Per-case inspection.
- Comparative report.
- Reproducible run instructions.
- Honest limitations.
- No fabricated real-world benchmark results.

This Core feature is complete only when all implemented evaluation components have passed relevant local verification. A live two-model comparison additionally requires available model credentials and must be reported as unverified until actually run.

---

## FEATURE C16 — DEPLOYMENT AND PORTFOLIO DELIVERY

### Purpose

Deliver a reproducible, professionally documented, portfolio-ready system.

### Must build

- Docker-based application setup.
- Database migration execution.
- Demo data initialization.
- Environment variable documentation.
- Backend startup instructions.
- Frontend startup instructions.
- Test execution instructions.
- Benchmark execution instructions.
- Health checks.
- Clear deployment configuration.
- One practical deployment target/configuration.
- Safe credential handling.
- Bounded public demo usage.
- Recovery/restart documentation.
- Accurate API documentation.
- Final architecture diagram.
- Data-flow diagram.
- Supported support scenarios.
- Security architecture summary.
- Benchmark report.
- Known limitations.
- Screenshots.
- Portfolio demonstration walkthrough.

## README requirements

The README should answer:

1. What does the project do?
2. Which problem does it solve?
3. What makes it technically interesting?
4. How does the architecture work?
5. Which real operations can it execute?
6. How does policy retrieval work?
7. How are actions authorized?
8. How is uncertainty handled?
9. How does human escalation work?
10. How is the system tested?
11. How is it evaluated?
12. What were the benchmark results?
13. What are the model/cost/latency tradeoffs?
14. What important failure modes exist?
15. How can the project be run locally?
16. How can the benchmark be reproduced?
17. What remains outside the current scope?

Keep documentation technical, clear, and evidence-backed.

Do not claim that a deployment exists unless it is actually deployed.

Do not claim measured performance without executing the measurement.

### Definition of Done

- Fresh installation works.
- Database setup works.
- Main application flows work.
- Demo data works.
- Tests pass.
- Evaluation runner works.
- Available benchmark evidence is documented accurately.
- Architecture documentation matches the actual implementation.
- Deployment configuration exists and is validated where possible.
- README is complete.
- Demonstration steps are reproducible.

---

# PART 7 — OPTIONAL STRONG PORTFOLIO ADDITIONS

Do not implement these automatically.

Once Core is complete, record the following as candidates.

## S01 — Retrieval Quality Improvements

Potential scope:

- Hybrid semantic/keyword retrieval.
- Reranking.
- Retrieval evaluation.
- Before/after retrieval comparisons.

Implement only if explicitly selected.

## S02 — Risk-Aware Escalation Calibration

Potential scope:

- Risk categories.
- Escalation policy rules.
- Calibrated uncertainty signals where justified.
- Automation/accuracy tradeoff evaluation.
- Escalation precision/recall comparisons.

Implement only if explicitly selected.

## S03 — Advanced Action Approval and Recovery

Potential scope:

- Pending action approvals.
- Stale approval rejection.
- Advanced retry/recovery.
- Selected reversible action compensation.
- Additional action-state auditing.

Implement only if explicitly selected.

## S04 — Benchmark Failure Analysis

Potential scope:

- Failure taxonomy.
- Failure classification.
- Trace-linked examples.
- Cost/latency breakdown.
- Root-cause-oriented engineering analysis.

Implement only if explicitly selected.

## S05 — Load and Performance Testing

Potential scope:

- Repeatable concurrent workloads.
- Throughput.
- Latency distributions.
- Database bottlenecks.
- One measurable performance improvement.

Implement only if explicitly selected.

## S06 — Continuous Evaluation Gates

Potential scope:

- Regression evaluation suite.
- Versioned evaluation baseline.
- Automated comparisons.
- Safety regressions.
- Historical evaluation reports.

Implement only if explicitly selected.

Do not allow any of these additions to delay completion of Core.

---

# PART 8 — EXPLICITLY DEFERRED FEATURES

Do not implement:

- Multi-organization architecture.
- Real payment provider integration.
- External helpdesk integrations.
- Advanced cross-channel support.
- Enterprise policy approval workflows.
- Distributed worker infrastructure unless necessary.
- Kubernetes.
- Microservices.
- Multi-agent architecture.
- Custom model training.
- Fine-tuning.
- Complex compliance infrastructure.
- Enterprise SSO.
- Large-scale monitoring clusters.
- Multiregion deployment.
- Features unrelated to the product's main value.

Small foundations that naturally support future extensibility are acceptable.

Do not spend substantial time implementing speculative extension mechanisms.

---

# PART 9 — CROSS-CUTTING ENGINEERING REQUIREMENTS

These requirements apply throughout the project.

## 9.1 Data integrity

- Enforce relationships and constraints.
- Use database transactions for consequential operations.
- Design mutating operations to be idempotent.
- Preserve authoritative business state.
- Handle concurrent modifications.
- Avoid incomplete or misleading success states.

## 9.2 Error handling

Every important failure should:

- Produce an appropriate application outcome.
- Avoid corrupting state.
- Be traceable.
- Be represented correctly to the user.
- Have enough diagnostic information to investigate.

Never expose raw sensitive stack traces through public APIs.

## 9.3 AI safety boundaries

- Treat generated model output as untrusted.
- Validate structured results.
- Enforce authorization independently.
- Restrict available tools.
- Limit model execution loops.
- Protect against instruction injection through retrieved documents.
- Avoid unsupported claims of completed actions.
- Escalate when necessary.

## 9.4 Data and policy consistency

The simulated business rules and published company policies must agree.

Do not create a refund policy document that permits an operation the backend always rejects unless that conflict is intentionally part of a labeled evaluation scenario.

Use explicitly defined policy fixtures.

## 9.5 Performance

- Avoid unnecessary database round trips.
- Apply pagination to potentially growing lists.
- Bound retrieved context.
- Bound provider requests.
- Bound expensive evaluation runs.
- Avoid obvious inefficient processing.
- Prefer measured optimization over premature complexity.

## 9.6 Maintainability

- Use clear names.
- Keep modules cohesive.
- Avoid duplicated business rules.
- Keep business logic out of route handlers.
- Maintain typed contracts.
- Use migrations.
- Make dependencies explicit.
- Write useful tests.
- Document non-obvious decisions.

## 9.7 Reproducibility

- Version model configurations.
- Version prompts.
- Version policy corpus.
- Version evaluation datasets.
- Preserve benchmark run metadata.
- Use deterministic test fixtures.
- Record relevant environment information.

## 9.8 Security

- Enforce resource ownership.
- Use least privilege.
- Protect secrets.
- Restrict costly endpoints.
- Avoid leaking sensitive data.
- Validate data across trust boundaries.
- Keep demo data synthetic.

---

# PART 10 — USER EXPERIENCE REQUIREMENTS

Every user-facing feature must be implemented with attention to how the user receives and understands the result.

For each UI workflow, consider:

1. What does the user expect to happen?
2. What should be visible before interaction?
3. What feedback should appear during processing?
4. How is success confirmed?
5. How is failure communicated?
6. Can the user understand what happened?
7. Can the user recover or try again safely?
8. Does the interface show the actual backend state?
9. Is information organized clearly?
10. Is the workflow consistent with the rest of the product?

Do not use excessive animation, decoration, or unnecessary interface complexity.

Optimize for a polished professional support operations dashboard.

The visual experience should reinforce the platform's engineering capabilities.

The most important visual demonstrations are:

- A grounded support answer with citations.
- A successful real business action.
- A rejected unsafe action.
- A human escalation and resolution.
- An inspectable processing trace.
- A comparative benchmark result.

---

# PART 11 — IMPLEMENTATION TRACKING AND QUALITY GATES

Create and maintain a feature tracker.

For every Core feature record:

- Feature ID.
- Scope.
- Implementation status.
- Main files/modules.
- Dependencies.
- Implemented APIs.
- Database changes.
- Tests created.
- Tests executed.
- Test results.
- Unresolved issues.
- Definition of Done status.
- Documentation updated.

## Completion gate

A feature is VERIFIED only when:

1. All Must Build requirements are implemented.
2. Required integrations are present.
3. Important failure cases are handled.
4. Appropriate tests exist.
5. Tests have been executed successfully.
6. No known critical correctness issue remains.
7. Documentation is updated.
8. The feature's specific Definition of Done is satisfied.

Do not treat a feature as complete because files were generated.

## Regression gate

After each major feature:

- Run its tests.
- Run affected integration tests.
- Check that earlier functionality remains intact.
- Correct newly introduced failures.

Before final delivery:

- Run the standard test suite.
- Run representative end-to-end scenarios.
- Verify database migrations.
- Verify demo seed initialization.
- Verify configuration instructions.
- Verify frontend/backend integration.
- Verify benchmark execution using available credentials.
- Review documentation against actual functionality.

---

# PART 12 — REQUIRED FINAL PROJECT STRUCTURE

Choose the exact directory structure based on maintainability and the framework conventions.

The repository should clearly contain logical homes for:

- Backend application.
- API routes.
- Domain models.
- Database access.
- Business services.
- Policy ingestion.
- Retrieval.
- Model gateway.
- AI orchestration.
- Tool execution.
- Response validation.
- Escalation.
- Authentication and authorization.
- Logging and observability.
- Evaluation.
- Unit tests.
- Integration tests.
- Frontend application.
- Database migrations.
- Seed/demo data.
- Configuration.
- Docker setup.
- Documentation.
- Benchmark artifacts.

Do not force a directory for every tiny component.

Use cohesive modules.

Avoid circular dependencies.

---

# PART 13 — END-TO-END ACCEPTANCE SCENARIOS

The complete project must support the following real application demonstrations.

## Scenario A — Policy question

Customer asks whether a subscription can be canceled.

Expected behavior:

1. Case is created.
2. Relevant cancellation policy is retrieved.
3. Model produces a grounded answer.
4. Valid citation is included.
5. Message is persisted.
6. Case state is updated.
7. Trace records the relevant processing.

## Scenario B — Valid subscription change

Customer requests a permitted plan change.

Expected behavior:

1. Case is created.
2. Customer identity/account is established.
3. Subscription is retrieved.
4. Policy evidence is checked.
5. Model proposes the correct action.
6. Backend validates eligibility.
7. Database state changes.
8. Action audit record is created.
9. Customer receives accurate confirmation.

## Scenario C — Eligible refund

Customer requests a refund for an eligible invoice.

Expected behavior:

1. Relevant invoice is identified.
2. Refund policy is retrieved.
3. Eligibility is established by backend logic.
4. Refund executes against simulated business state.
5. Refund record persists.
6. Duplicate refund attempts are prevented.
7. Customer receives verified confirmation.

## Scenario D — Unauthorized action

Customer requests a change to another account.

Expected behavior:

1. Target account is identified.
2. Authorization is checked.
3. Unauthorized operation is rejected.
4. No unauthorized state mutation occurs.
5. Appropriate response is returned.
6. Rejection is traceable.

## Scenario E — Ambiguous request

Customer asks for an action without sufficient identifying information.

Expected behavior:

1. Missing information is detected.
2. No unsafe guess is made.
3. Customer receives a specific clarification question.
4. Case awaits customer response.
5. Follow-up can continue the workflow.

## Scenario F — Required escalation

Customer presents a case with conflicting or insufficient policy evidence.

Expected behavior:

1. Relevant policy evidence is retrieved.
2. Uncertainty or conflict is detected.
3. Automated resolution is withheld.
4. Escalation record is created.
5. Operator sees the relevant context.
6. Operator resolves or requests clarification.
7. Case history and final outcome persist.

## Scenario G — Model/provider failure

A model request fails during processing.

Expected behavior:

1. Failure is classified.
2. No unverified business action is reported as completed.
3. Case moves into a safe recoverable or failed state.
4. Diagnostic trace is preserved.
5. Customer receives an appropriate non-misleading message.

## Scenario H — Benchmark comparison

An evaluator runs two model configurations.

Expected behavior:

1. The same versioned dataset is loaded.
2. Business fixtures are controlled.
3. Policies are consistent across runs.
4. Both configurations use the real processing path.
5. Decisions and actions are graded.
6. Failures are retained.
7. Cost and latency are recorded.
8. Escalation and safety metrics are calculated.
9. A comparative report is produced.
10. Results and configurations are inspectable.

Do not mark the complete product as ready if the corresponding acceptance scenarios are not working.

---

# PART 14 — FINAL DELIVERY REQUIREMENTS

At completion, provide a concise engineering delivery report.

Include:

## 1. Implemented feature summary

State which Core features are VERIFIED, unverified, or blocked.

## 2. Architecture overview

Explain the main components and how they interact.

## 3. How to run

Provide exact startup, migration, seed, and test commands.

## 4. Demo walkthrough

Provide steps for the most important successful and failure scenarios.

## 5. Evaluation results

Provide actual benchmark artifacts and measured results, if executed.

If real-model runs were blocked, say so explicitly.

## 6. Testing evidence

List the test commands executed and their outcomes.

## 7. Known limitations

Explain important limitations honestly.

## 8. Engineering decisions

Summarize significant tradeoffs and why they were made.

## 9. Strong Addition candidates

List optional enhancements without implementing them.

---

# PART 15 — START EXECUTION

Begin implementing the project now.

Your first actions:

1. Inspect the repository and existing files.
2. Determine whether the repository is empty or contains reusable code.
3. Review current stable dependency compatibility.
4. Establish the overall architecture.
5. Create the feature tracker.
6. Create the requirements-to-tests traceability document.
7. Establish the repository structure.
8. Begin Core Feature C01.
9. Implement and test C01.
10. Continue through the Core feature sequence while respecting the completion gates.

Do not spend the session generating a long speculative planning document instead of implementing the project.

The planning artifacts should be concise and immediately useful.

After every feature, provide a short structured progress report containing:

- Feature completed.
- Main functionality delivered.
- Tests executed and results.
- Important design choices.
- Any blocker or limitation.
- Next feature.

Persist meaningful progress in the repository so the next Codex session can resume without depending on chat history.

Do not skip verification simply to move faster.

Do not silently reduce the scope.

Do not implement Strong Additions without explicit approval.

Do not misrepresent test, deployment, or benchmark outcomes.

The final goal is a complete, genuinely functional, technically credible AI Support Operations Platform that demonstrates real applied AI engineering, software design, safety, reliability, evaluation, and production-minded development.

**Start with C01 and proceed in dependency order.**
