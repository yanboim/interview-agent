# Agent application hardening and capability program

- Status: completed
- Date: 2026-07-30
- Owner: agent platform and product engineering
- Technical debt: TD-014, TD-015, TD-016, TD-017
- Product contract: add contracts per milestone; do not change existing
  `passing` entries without executable verification

## Objective

Move Interview Agent from prompt-routed specialist chat toward a safe,
grounded, personalized, measurable, and recoverable agent application. Deliver
the work as small milestone PRs rather than one rewrite, preserving the current
chat/interview lifecycle, server-resolved ownership, model gateway, and
versioned knowledge publication boundaries.

The program covers the fifteen gaps identified in the 2026-07-29 review:
agent orchestration, delegated context, long-term memory, profile/JD context,
specialist grounding, claim-level citations, prompt injection, search DLP,
audit privacy, confirmation for mutations, structured output, end-to-end
evaluation, durable user feedback, calibrated learning, and model
cost/resilience.

## Non-goals

- Replace the modular monolith with microservices.
- Give the model direct database, filesystem, administrator, or arbitrary HTTP
  access.
- Use hidden chain-of-thought as a product or audit artifact.
- Automatically write inferred personal facts into durable memory without user
  confirmation.
- Add a second external model provider before privacy, cost, and evaluation
  approval.
- Run live model/RAG evaluations in the default local or CI gate.

## Program acceptance criteria

- Tool audits contain identifiers, counts, status, duration, and safe error
  classes only; tests prove that prompts, PII, credentials, and private
  knowledge text cannot be copied into generic audit or trace tables.
- Public-search queries pass deterministic DLP and untrusted-content policy;
  sensitive or ambiguous queries require explicit confirmation and cannot be
  replayed with changed content.
- Every mutating agent action follows `preview -> awaiting_confirmation ->
  applied|cancelled|expired`, with an owner-bound, content-bound,
  single-use confirmation token.
- Chat and specialist calls receive one server-built, budgeted context
  snapshot containing only task-relevant profile, JD, memory, history, and
  evidence. Users can inspect, correct, or delete durable coaching memory.
- Scoring and high-impact feedback use validated structured outputs and
  grounded evidence where available. Important answer claims expose
  claim-to-source mappings rather than a turn-level “knowledge used” flag.
- At least one personalized training workflow is a durable, recoverable agent
  run with explicit run/step state and idempotent command execution.
- Evaluation invokes the real agent stack and gates routing, multi-turn
  delegation, grounding, structured output, tool failure, injection defense,
  confirmation, latency, and cost. User feedback is persisted by turn and can
  feed a reviewed evaluation-candidate queue.
- Capability and review scheduling incorporate sample confidence, recency,
  difficulty, and recall outcome; existing histories remain readable and are
  recomputed deterministically.
- Each milestone passes focused tests, `make docs-check`, and
  `make harness-check`. Cost-bearing live evaluations run only in an approved
  environment and attach their report to the milestone.

## Milestone 0 — Baseline and immediate safety

1. Preserve and verify the in-progress bounded-runtime/context work already
   present on 2026-07-30:
   - delegated specialists inherit the budgeted conversation context through
     `app/agent_context.py`;
   - synchronous and streaming chat enforce `chat_agent_timeout_seconds` and
     `agent_recursion_limit`;
   - timeouts terminate the durable chat turn with a safe client error.
2. Replace tool audit `input_summary` and `result_summary` payloads with a
   typed safe-metadata object. Knowledge search records query hash/length,
   knowledge version, source IDs, result count, score bucket, status, and
   duration—never query text or chunk text.
3. Add a shared outbound-data policy for public search:
   - normalize and classify the proposed query;
   - reject credentials, PII, resume/transcript fragments, private-source
     excerpts, and high-entropy secrets;
   - allow only minimal public keywords by default;
   - return a confirmation preview when classification is ambiguous.
4. Wrap retrieved knowledge and web snippets as explicitly untrusted evidence.
   Specialist prompts must state that evidence content is data, never
   executable instruction. Add malicious-document and malicious-web-snippet
   regression cases.
5. Split learning-plan mutation into preview and confirm commands. Persist the
   preview digest and expiry; apply it once using server-resolved `user_id` and
   the existing task deduplication boundary.

Milestone verification:

- Unit tests for audit redaction, DLP classifications, injection cases, token
  ownership/content binding, expiry, replay, cancellation, and timeout.
- Migration tests if confirmation state is stored relationally.
- Negative authorization tests for cross-user confirmation.

## Milestone 1 — Grounded and typed agent outputs

1. Add versioned Pydantic schemas for delegation, specialist result, scoring,
   training-plan preview, and answer citations. Use provider structured output
   when supported; otherwise use one bounded schema-repair attempt through the
   model gateway and fail safely.
2. Replace the greedy JSON extraction paths in interview scoring, resume
   analysis, and interview review without changing their public response
   shapes. Persist `prompt_version`, `schema_version`, and `model_version` for
   every generated artifact and chat execution trace.
3. Give Interviewer and Evaluator read-only access to the private retrieval
   service. Retrieval is optional for ordinary behavioral questions but
   required for factual corrections that are not supported by the supplied
   question/answer context.
4. Return stable source/chunk identifiers from retrieval. The final specialist
   result maps each material claim to zero or more evidence IDs and labels
   unsupported claims explicitly.
5. Extend streaming metadata with a versioned citation event. Keep the current
   turn-level source list for compatibility until the frontend and stored
   history can render claim-level citations.

Milestone verification:

- Schema-valid, malformed, truncated, multi-object, unsupported-claim, source
  conflict, and retrieval-unavailable tests.
- Frontend tests for inline citations, unsupported-answer state, replayed
  metadata, and backward-compatible historical messages.

## Milestone 2 — Personalized context and durable memory

1. Introduce an application-owned `AgentContextService` that builds one
   immutable snapshot per turn from:
   - authenticated identity and role;
   - target role, experience level, focus areas, interview date, and JD;
   - selected durable coaching memories;
   - budgeted conversation summary and recent messages;
   - relevant capability weaknesses and due learning tasks.
2. Replace raw delegated task strings with a versioned `DelegationEnvelope`
   carrying the user goal, original request, relevant prior turns, evidence,
   constraints, expected output schema, and correlation IDs. Do not duplicate
   the full chat transcript in every specialist call.
3. Add owner-scoped durable coaching memory with three states:
   `proposed`, `confirmed`, and `rejected`. Only confirmed user facts,
   preferences, and goals may enter future contexts. Derived training
   observations remain source-linked and expire or recompute when their source
   artifact changes.
4. Add product UI and API operations to inspect, confirm, correct, reject, and
   delete memory. Deletion removes it from future snapshots immediately while
   leaving canonical interview/chat history unchanged.
5. Continue using the existing deterministic context compaction for recent
   chat continuity, but stop treating assistant excerpts as durable user
   facts.

Milestone verification:

- Migration, ownership, snapshot-budget, stale-source, correction, deletion,
  and cross-session continuity tests.
- E2E scenarios for changing a target role, correcting a memory, and confirming
  that a subsequent specialist uses the corrected value.

## Milestone 3 — Durable agent workflow

1. Add application-owned `agent_runs` and `agent_steps` records rather than
   making LangGraph storage the business source of truth. A run uses:
   `proposed -> awaiting_confirmation -> running -> completed|failed|cancelled`;
   a step uses `pending -> claimed -> completed|failed|skipped`.
2. Build `AgentRunService` as the transaction/concurrency boundary. Every
   command step has a stable idempotency key, input digest, claim owner, and
   stored result replay. External model/tool calls remain outside database
   transactions.
3. Deliver one narrow workflow first: “personalized training program.”
   It reads profile/capability/task state, proposes prioritized training,
   requests confirmation, then creates deduplicated learning tasks and returns
   a link to the existing interview creation flow. It does not silently start
   an interview or alter a resume.
4. Stream user-visible run events (`planned`, `waiting_confirmation`,
   `step_started`, `step_completed`, `failed`, `done`) without exposing hidden
   reasoning. Users can cancel before any unstarted command step.
5. Add operator recovery for abandoned claimed steps. Recovery may retry only
   read-only/model steps automatically; command steps rely on stored
   idempotency and result replay.

Milestone verification:

- Concurrent confirmation, duplicate command, crash/reclaim, cancellation,
  partial failure, stored replay, and user isolation tests.
- E2E completion of the personalized training workflow from proposal through
  created tasks.

## Milestone 4 — Evaluation, feedback, and learning quality

1. Replace metadata-only answer evaluation with real agent execution against a
   frozen corpus and deterministic mocked provider in CI. Maintain a separate
   approved live-model report.
2. Expand versioned evaluation sets to cover at minimum:
   - 100 routing cases, including ambiguity and multi-intent;
   - 50 grounded-answer cases with claim-level labels;
   - 30 multi-turn/delegation cases;
   - 30 tool failure, DLP, and prompt-injection cases;
   - 20 confirmation/workflow cases.
3. Define gates per group rather than only overall averages. Any privacy,
   unauthorized mutation, source fabrication, or cross-user case has a zero
   tolerated-failure threshold.
4. Persist thumbs-up/down against the durable assistant message/turn ID, with
   optional reason codes and free text. Store model/prompt/schema versions and
   source IDs; enqueue negative feedback as an evaluation candidate only after
   privacy review.
5. Calibrate scoring with versioned, human-labelled examples. Capability
   aggregation records sample count and confidence, applies configured recency
   weighting, and compares like topic/difficulty/model-version cohorts.
6. Record recall outcome or user-rated difficulty when reviewing a learning
   task. Replace count-only intervals with a deterministic scheduler that uses
   outcome, lapse count, and confidence while preserving a bounded interval.

Milestone verification:

- Evaluation-report schema tests, minimum dataset-size checks, feedback
  ownership tests, scoring calibration cases, and deterministic scheduler
  migration tests.
- Product metrics for feedback rate, grounded-claim coverage, confirmation
  abandonment, workflow completion, score confidence, and review recall.

## Milestone 5 — Cost, latency, and provider resilience

1. Add per-purpose model configuration for supervisor/router, knowledge,
   interviewer, evaluator, planner, summarization, and schema repair. Defaults
   preserve the current configured model.
2. Permit a deterministic intent classifier or approved low-cost model to skip
   the Supervisor model call for high-confidence single-intent requests.
   Ambiguous/multi-intent requests continue through the Supervisor.
3. Record per-run call count, input/output tokens, wall time, first-token time,
   and configured price version. Define budgets by request class and stop
   before an additional specialist call would exceed the budget.
4. Add an optional same-provider fallback model only after it passes the
   relevant evaluation gates. Never fall back scoring or resume/review analysis
   across uncalibrated model versions; return a recoverable unavailable state
   instead.
5. Roll out model routing behind feature flags: internal evaluation, canary,
   then production. Compare quality, p95 latency, completion rate, and cost per
   completed training action against the preserved single-model path.

Milestone verification:

- Routing/fallback policy tests, budget exhaustion, metrics labels, unavailable
  state, and feature-flag rollback.
- Approved canary report showing no privacy/quality gate regression.

## API, schema, and compatibility changes

- Add versioned endpoints for agent-action preview/confirmation, durable agent
  runs/events, coaching memory management, and turn feedback.
- Add relational tables for action confirmations, coaching memories,
  `agent_runs`, `agent_steps`, and message feedback. Every owner-scoped table
  includes `user_id`; every schema change uses Alembic and migration tests.
- Extend chat source metadata additively with evidence IDs and claim mappings.
  Existing clients may continue reading the current source list.
- Preserve current chat/interview endpoint behavior and durable idempotency.
  New agentic workflows call application services rather than duplicating
  their persistence logic.

## Delivery order and sizing

Implement as 10–14 reviewable PRs over approximately 8–12 engineer-weeks for
one experienced full-stack engineer, excluding external privacy approval and
live-model labelling time:

1. Milestone 0: 1.5–2 weeks.
2. Milestone 1: 1.5–2 weeks.
3. Milestone 2: 1.5–2 weeks.
4. Milestone 3: 2–3 weeks.
5. Milestone 4: 1.5–2.5 weeks.
6. Milestone 5: 1–1.5 weeks.

Milestones 0 and 1 are release blockers for expanding agent actions. Milestone
2 precedes Milestone 3. Dataset preparation for Milestone 4 may run alongside
Milestones 1–3, but quality gates become authoritative only after the real
execution harness exists. Milestone 5 starts after Milestone 4 establishes
quality baselines.

## Progress

- [x] Re-read architecture, feature contract, technical-debt tracker, current
      agent/runtime code, evaluation scripts, and active plans.
- [x] Recorded the 2026-07-30 partial context propagation and runtime-bound
      implementation as Milestone 0 verification work rather than redesigning
      it.
- [x] Completed the first Milestone 0 safety slice: content-free tool audits,
      public-search DLP, explicit untrusted-evidence wrappers, and owner-bound
      single-use learning-plan preview/confirmation. Added migration 0017 and
      the `agent-tool-safety-boundary` executable product contract.
- [x] Added owner-bound explicit confirmation for ambiguous but potentially
      safe outbound public-search queries. Sensitive categories remain
      rejected; confirmed queries execute at most once and replay stored
      results without another network request.
- [x] Verified the first safety slice with `make harness-check` on 2026-07-30:
      17 static architecture/contract tests, 228 backend tests (2 skipped),
      18 frontend unit tests, production build/bundle budgets, and 24 browser
      E2E tests passed.
- [x] Implemented and verified Milestone 0 on 2026-07-31. Final verification:
      17 static architecture/contract tests, 231 backend tests (2 skipped),
      18 frontend unit tests, production build/bundle budgets, and 24 browser
      E2E tests passed. TD-014 is complete.
- [x] Implemented and verified Milestone 1 on 2026-07-31. Added versioned
      contracts, native/one-repair structured output, stable evidence IDs,
      claim-level citation streaming/replay, read-only specialist retrieval,
      and generated-artifact provenance migration 0018. Final verification:
      17 static tests, 239 backend tests (2 skipped), 19 frontend unit tests,
      production build/bundle budgets, and 24 browser E2E tests passed.
- [x] Implemented the Milestone 2 application slice on 2026-07-31: immutable
      budgeted `AgentContextService` snapshots, versioned single-envelope
      delegation, owner-scoped proposed/confirmed/rejected coaching memory,
      stale derived-memory filtering, memory management API/UI, and migration
      0019. Focused verification passed with 3 context/memory tests, 19
      frontend unit tests, type checking, and 2 desktop/mobile memory E2E
      scenarios.
- [x] Implemented and verified Milestone 2 on 2026-07-31. Added migration 0019
      and the `agent-personalized-context-memory` executable product contract.
      Final verification: 17 static architecture/contract tests, 242 backend
      tests (2 skipped), 19 frontend unit tests, production build/bundle
      budgets, and 24 browser E2E tests passed.
- [x] Implemented the Milestone 3 application slice on 2026-07-31: durable
      `agent_runs`/`agent_steps`, idempotent and owner-fenced commands, stored
      replay, cancellation/retry/stale-claim recovery, lifecycle SSE,
      minimized administrator inspection, and the confirmed personalized
      training workflow UI. Focused service/API/migration, frontend, and
      desktop/mobile E2E verification passed. Repository-wide gate results
      are recorded below once run.
- [x] Implemented and verified Milestone 3 on 2026-07-31. Added migration
      0020, closed TD-016, and added the
      `durable-personalized-training-workflow` executable product contract.
      Final verification: 17 static architecture/contract tests, 250 backend
      tests (2 skipped), 21 frontend unit tests, production build/bundle
      budgets, and 26 browser E2E tests passed.
- [x] Implemented the Milestone 4 quality loop on 2026-07-31. Added migration
      0021; durable owner-scoped turn feedback and privacy-reviewed negative
      evaluation candidates; a versioned deterministic 230-case real-stack
      suite with group and zero-tolerance gates; human-labelled calibration,
      recency/confidence/cohort aggregation; outcome-aware bounded review
      scheduling; and product quality metrics. Closed TD-015 and added the
      `agent-quality-feedback-learning-loop` executable contract. Full
      repository gate results are recorded after documentation generation.
- [x] Implemented the Milestone 5 model-cost-resilience slice on 2026-07-31:
      per-purpose model configuration (including schema repair), deterministic
      high-confidence direct routing behind off/internal/canary/production
      stages, request-class call/token/cost budgets with first-token and price
      telemetry, evaluation-approved same-provider fallback, high-impact
      unavailable policy, and an approved deterministic canary/rollback
      report. Closed TD-017 and added the
      `agent-model-cost-resilience-routing` executable contract. Final
      repository-wide verification is recorded below.
- [x] Audited all 6 milestones and 31 tasks, then passed `make harness-check`
      on 2026-07-31: the versioned 230-case Agent application-stack gate and
      all group/zero-tolerance thresholds passed; 17 static architecture,
      contract, documentation, and reproducibility tests passed; 270 backend
      tests passed with 2 external-PostgreSQL conditional skips; 22 frontend
      unit tests, type checking, production build, and bundle budgets passed;
      and all 26 desktop/mobile Playwright E2E tests passed.

## Decisions and rollout

- Security and truthfulness precede additional autonomy.
- The relational store remains authoritative for user-owned run/action state;
  LangGraph remains an orchestration implementation detail.
- All model-proposed mutations require explicit confirmation; read-only
  retrieval does not.
- Existing history is migrated additively. New memory and feedback features
  start empty; they do not infer or backfill user facts from old conversations.
- Each milestone is independently feature-flagged and rollbackable. Schema
  rollback uses forward corrective migrations; do not destructively drop user
  data during rollout.
