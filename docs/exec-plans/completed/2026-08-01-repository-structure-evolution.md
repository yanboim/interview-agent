# Repository structure evolution

- Status: completed
- Date: 2026-08-01
- Owner: repository maintainers
- Responsible roles: backend, frontend, quality, and operations maintainers

## Objective

Evolve the repository from a sound first-stage modular monolith into a more
explicitly bounded product workspace without a flag-day rewrite. Reduce the
largest maintenance hotspots, move complete use-case orchestration out of HTTP
adapters, make runtime code independent from command scripts, and preserve the
existing reliability, security, evaluation, deployment, and documentation
gates throughout the transition.

## Why now

The repository-level layout is healthy: backend, frontend, migrations, tests,
Agent evaluation, documentation, deployment, and monitoring are separate and
participate in one Harness. The next scaling constraints are inside those
boundaries:

- `app/storage.py` is a multi-domain persistence implementation exceeding four
  thousand lines;
- chat routing, Agent execution, evidence extraction, tracing, and completion
  remain coordinated by the HTTP router;
- `app/tools.py` and `app/operations.py` mix several infrastructure and runtime
  responsibilities;
- production application wiring imports knowledge-ingestion implementation
  from `scripts/`;
- backend tests and command scripts are still flat collections;
- production knowledge seeds, runtime knowledge, local data, backups, and test
  artifacts need clearer ownership;
- the release packaging workflow does not itself consume the complete canonical
  Harness gate.

These are evolutionary boundary problems. They do not justify replacing the
modular monolith, database, queue, RAG publication flow, or frontend stack.

## Non-goals

- Split the application into network microservices.
- Introduce a `backend/src/` relocation or move every existing module at once.
- Replace PostgreSQL, Redis, Qdrant, Vue, FastAPI, LangChain, or LangGraph.
- Reimplement completed chat/interview idempotency, Redis lease/fencing, model
  gateway, confirmation, structured-output, or Qdrant alias behavior.
- Change public API paths or response shapes as an incidental refactor.
- Add a mandatory persistent LangGraph checkpointer to ordinary chat turns.
- Move production/user data automatically or delete local backups and artifacts.
- Mix product features or unrelated visual changes into structural pull requests.

## Architecture and product constraints

- Preserve the dependency direction documented in `ARCHITECTURE.md`: API
  adapters call application services, deterministic domain policy remains
  infrastructure-free, and infrastructure implements application-facing ports.
- Keep external model/network calls outside database transactions.
- Preserve server-resolved ownership, idempotency keys, owner fencing, bounded
  budgets, safe errors, evidence isolation, and preview/confirmation semantics.
- Alembic remains authoritative for production schema changes. Most tasks in
  this plan should require no migration; any exception becomes a separate plan.
- Existing `passing` feature contracts remain passing. Contract changes require
  executable verification and an explicit compatibility decision.
- `make harness-check` remains the repository completion gate. Live/cost-bearing
  model or RAG evaluation remains opt-in.

## Delivery principles

1. Prefer behavior-preserving extraction before behavior replacement.
2. Keep each change independently reviewable and reversible.
3. Introduce ports at real volatile boundaries, not for every function.
4. Do not run two structural changes over the same hotspot concurrently.
5. New files use the target boundary; legacy files move only when their behavior
   is already under focused tests.
6. A directory move alone is not an accepted deliverable.

## Workstream map

```text
RS-00 Baseline and decisions
  |-- RS-01 Complete ChatUseCase extraction
  |     `-- RS-04 Explicit chat workflow V2
  |            `-- RS-05 Retire nested Supervisor after canary
  |-- RS-02 Shared question/evaluation capabilities --'
  |-- RS-03 Test taxonomy and fixtures
  |-- RS-06 Persistence decomposition
  |-- RS-07 Runtime/script boundary
  |-- RS-08 Tool and operations decomposition
  |-- RS-09 Knowledge/runtime-data ownership
  |-- RS-10 Release-gate alignment
  `-- RS-11 Documentation and root hygiene
```

RS-01 and RS-02 may be prepared in parallel only when they do not edit the same
Agent assembly modules. RS-04 starts only after both application boundaries are
stable. RS-06 must be sliced by domain and must not overlap a use-case change in
the same domain.

## Task backlog

### RS-00: Freeze the baseline and record boundary decisions

- Priority: P0 planning gate
- Risk: low
- Change class: documentation, evaluation, architecture tests
- Depends on: none

Actions:

1. Record current route accuracy, grouped Agent evaluation, model-call count,
   estimated cost, p95 latency where available, citation coverage, chat
   completion, and confirmation/workflow completion baselines.
2. Inventory imports and ownership for `chat.py`, `storage.py`, `tools.py`,
   `operations.py`, `scripts/ingest.py`, and `scripts/worker.py`.
3. Write focused decisions for the Chat Use Case boundary, repository split
   strategy, workflow state/checkpoint policy, and knowledge seed/runtime model.
4. Convert the decisions into mechanical architecture checks where practical.

Acceptance criteria:

- Baseline datasets and reports are versioned and reproducible.
- Each subsequent task has an explicit owner, affected contracts, rollback, and
  focused verification command.
- No stale automated audit finding is treated as confirmed without manual code
  validation. In particular, fixed internal Redis Lua scripts are not classified
  as arbitrary untrusted-code execution.

Verification:

- `make harness-static`
- `python -m scripts.evaluate_agent_stack`

### RS-01: Extract a complete Chat Use Case

- Priority: P0 structural
- Risk: medium
- Change class: behavior-preserving application-boundary refactor
- Depends on: RS-00

Actions:

1. Define `ChatCommand`, `ChatResult`, and application-facing ports for Agent
   execution, trace recording, and completed-answer metadata.
2. Move turn claim/replay, route selection, budget scope, Agent invocation,
   evidence/citation projection, completion, failure, timeout, and cancellation
   coordination behind one application use case.
3. Keep HTTP concerns in the router: authentication, header/schema validation,
   HTTP/stream response serialization, disconnect signal, and error mapping.
4. Preserve ordinary and streaming endpoint behavior and existing idempotent
   replay semantics.

Acceptance criteria:

- Chat routers do not construct/select models or directly invoke an Agent.
- Chat routers do not own persistence completion or citation business rules.
- Sync and stream paths use the same application orchestration contract.
- No public API, stored metadata, timeout, cancellation, or replay regression.
- Architecture tests prevent Agent/model invocation from returning to routers.

Focused verification:

- `pytest -q tests/test_chat_lifecycle.py tests/test_main.py tests/test_agent_io.py`
- affected frontend chat API/store tests
- `make harness-check`

Rollback:

- Restore the prior router orchestration while keeping unchanged public and
  persistence contracts. No data migration is expected.

### RS-02: Unify question generation and answer evaluation

- Priority: P0 structural and quality
- Risk: medium
- Change class: application/domain capability extraction
- Depends on: RS-00

Actions:

1. Define shared `QuestionGenerator`, `AnswerEvaluator`, and report-building
   application contracts with versioned request/result schemas.
2. Make formal interviews and chat interviewer/evaluator nodes call the shared
   capability rather than maintain separate prompt/output implementations.
3. Preserve resume-grounded interview inputs and the existing four-dimensional
   persisted assessment response.
4. Version prompts, schemas, models, and evaluation cohorts explicitly.

Acceptance criteria:

- One authoritative scoring rubric and structured assessment schema exist.
- Chat and formal interview adapters no longer maintain independent scoring
  parsing or incompatible prompts.
- Existing interview API/persistence behavior remains compatible.
- Frozen evaluation gates show no regression by topic, difficulty, source type,
  or model version.

Focused verification:

- `pytest -q tests/test_interview_engine.py tests/test_interview_idempotency.py tests/test_multi_agent.py tests/test_resume_grounded_interview.py`
- affected Agent evaluation scripts and reports
- `make harness-check`

### RS-03: Introduce backend test taxonomy without a mass move

- Priority: P1 enablement
- Risk: low
- Change class: test organization
- Depends on: RS-00

Actions:

1. Establish conventions for `unit`, `application`, `contract`, `integration`,
   `architecture`, `migration`, and `fault_injection` tests.
2. Put new tests into the appropriate group; move existing files only when they
   are already being changed for another task.
3. Centralize reusable factories/fixtures without creating an all-purpose
   fixture module.
4. Keep current direct test paths available until Makefile and CI selectors are
   updated atomically.

Acceptance criteria:

- Developers can identify test environment and cost from its directory.
- Unit/default tests do not silently require Redis, PostgreSQL, Qdrant, browser,
  or live model credentials.
- CI and local focused-test commands remain deterministic.

Verification:

- `make backend-check`
- `make harness-static`

### RS-04: Add explicit chat workflow V2 behind the existing rollout controls

- Priority: P1 product architecture
- Risk: high
- Change class: Agent behavior and orchestration
- Depends on: RS-01, RS-02, RS-03

Actions:

1. Implement explicit guard, context, route, specialist execution, verification,
   composition, and persistence stages behind an application-owned runner.
2. Reuse deterministic high-confidence routing first. Use structured model
   classification only for unresolved or genuinely multi-intent requests.
3. Represent multi-intent execution as a bounded dependency graph; parallelize
   only independent nodes.
4. Generate known execution plans in code. Do not add a planning-model call to
   every request.
5. Reuse current budget, context snapshot, evidence, confirmation, model gateway,
   trace, and evaluation capabilities.
6. Keep ordinary chat workflow state in the durable chat turn plus safe trace;
   add checkpoints only for workflows whose recovery semantics require them.

Acceptance criteria:

- Every stage has strict input/output contracts, timeout, budget, safe failure,
  metrics, and isolated tests.
- Model-selected side effects still require owner/content-bound confirmation.
- A process crash cannot allow a stale owner to overwrite a newer result.
- V2 meets grouped non-regression thresholds for quality, safety, latency, cost,
  and completion before canary expansion.
- The existing path remains an immediate tested rollback.

Verification:

- workflow, routing, safety, context, budget, confirmation, and crash/retry tests
- deterministic Agent quality gate
- internal and canary comparison report
- `make harness-check`

### RS-05: Retire nested Supervisor orchestration

- Priority: P1 cleanup after evidence
- Risk: medium
- Change class: compatibility removal
- Depends on: RS-04 production approval

Actions:

1. Progress through internal and canary rollout using retained comparison
   baselines. For retirement, use either the public-production observation gate
   or the separately defined first-public-release pre-release acceptance gate.
2. Update the `agent-routing-contract` product behavior and verification before
   removing the old tool topology.
3. Remove nested specialist-as-tool execution only after rollback criteria and
   the applicable production-observation or pre-release acceptance gate passes.
4. Retain historical prompt/schema/model provenance for replayed results.

Acceptance criteria:

- Production requests no longer require nested Supervisor-to-specialist ReAct
  loops.
- No zero-tolerance privacy, unauthorized mutation, fabricated-source, or
  cross-user failure occurs in the approved gate.
- Cost, p95 latency, and completion are non-regressive against the retained
  baseline.
- Contract, docs, admin topology, tests, and rollback runbook match reality.

### RS-06: Decompose persistence by domain ports

- Priority: P1 maintainability
- Risk: high if attempted as one change; medium per slice
- Change class: persistence refactor
- Depends on: RS-00; affected domain use-case boundary must already be stable

Actions:

1. Define small application-facing repository protocols by aggregate rather
   than one universal Store interface.
2. Extract implementations one domain at a time: chat, interview, resume/review,
   learning/Agent runs, then audit/administration.
3. Share the existing Engine and transaction conventions; do not introduce a
   database-per-module or distributed transaction.
4. Keep atomic multi-table transition scripts together even if they span table
   definitions.
5. Remove compatibility methods only after all callers and tests migrate.

Acceptance criteria:

- Application services depend on narrow repository contracts.
- No extracted repository imports API or Agent composition modules.
- Transaction, concurrency, idempotency, ownership, and query-count behavior are
  preserved with focused tests.
- `storage.py` shrinks through completed domain slices, not mechanical line moves.

Verification:

- affected storage/application/API tests per slice
- migration and PostgreSQL checks when configured
- `make harness-check` for each repository-wide slice

### RS-07: Make `scripts/` thin command entrypoints

- Priority: P1 dependency hygiene
- Risk: medium
- Change class: runtime boundary refactor
- Depends on: RS-00

Actions:

1. Move reusable knowledge-ingestion coordination and Worker handlers into
   application/infrastructure modules.
2. Keep argument parsing, operator confirmation, exit codes, and process startup
   in `scripts/`.
3. Prevent `app/` from importing `scripts/` with an architecture test.
4. Group future scripts by operations, evaluation, documentation, migration, and
   development purpose only when selectors/imports can remain stable.

Acceptance criteria:

- Product/runtime modules never import `scripts.*`.
- CLI commands preserve documented invocation and safe confirmation behavior.
- Worker startup, ingestion, backup/restore, and evaluation tests remain green.

Focused verification:

- `pytest -q tests/test_ingest.py tests/test_worker.py tests/test_backup_restore.py tests/test_architecture.py`
- `make harness-check`

### RS-08: Decompose Tool and Operations modules by capability

- Priority: P2 maintainability
- Risk: medium
- Change class: infrastructure and Agent adapter refactor
- Depends on: RS-01, RS-07

Actions:

1. Separate Redis jobs, rate limiting, heartbeat, metrics, and operational read
   models without changing Lua/lease/fencing semantics.
2. Separate knowledge, public-search, and learning tools while preserving one
   policy gateway for model-selected outbound or side-effecting operations.
3. Do not force deterministic domain functions and normal repository calls
   through the Tool Gateway.
4. Preserve safe audit summaries and untrusted-evidence boundaries.

Acceptance criteria:

- Module names reflect one operational capability.
- Queue claim/ACK/retry/DLQ and confirmation/idempotency behavior is unchanged.
- Tools cannot bypass identity, DLP, confirmation, timeout, audit, or budget
  enforcement.

Verification:

- `pytest -q tests/test_operations.py tests/test_redis_jobs_integration.py tests/test_agent_tools.py tests/test_agent_contracts.py`
- `make harness-check`

### RS-09: Define knowledge seed, runtime data, and artifact ownership

- Priority: P2 repository and data governance
- Risk: medium because data moves can be destructive
- Change class: design first; migration only with explicit approval
- Depends on: RS-00

Actions:

1. Classify repository knowledge files as versioned seed, public sample, private
   operator input, or evaluation fixture.
2. Define whether container images carry seed content and how a runtime knowledge
   volume is initialized without hiding image content unexpectedly.
3. Keep user/private/operator knowledge and backups outside source control.
4. Propose a `.var/` or external-volume convention for local databases, backups,
   test traces, and runtime files.

Acceptance criteria:

- Every knowledge/data directory has an owner, lifecycle, backup policy, and
  external-processing classification.
- Image, volume, and ingestion semantics are documented and tested.
- No existing data is moved or deleted without an explicit recovery plan and
  operator confirmation.

### RS-10: Align release packaging with the canonical Harness

- Priority: P1 delivery reliability
- Risk: low to medium
- Change class: CI/CD
- Depends on: RS-00

Actions:

1. Ensure a release artifact is produced only from a source revision whose
   canonical static, backend, frontend, and E2E gates have passed.
2. Avoid running identical expensive suites twice when a trustworthy workflow
   dependency or reusable workflow can carry the result.
3. Preserve immutable dependency/image checks, artifact checksums, environment
   approval, and release ledger behavior.

Acceptance criteria:

- Release packaging has a mechanically enforceable dependency on the complete
  repository gate.
- A failed Agent evaluation, documentation check, architecture check, migration,
  frontend E2E, or security scan prevents promotable artifact creation.
- Canary/production approval and rollback remain documented.

Verification:

- workflow contract tests
- one non-production release-candidate exercise
- `make harness-check`

### RS-11: Consolidate documentation and root workspace hygiene

- Priority: P2 governance
- Risk: low for docs; high for deleting/moving local data
- Change class: documentation and conventions
- Depends on: active documentation plans complete; RS-09 decision

Actions:

1. Keep root documentation limited to repository entrypoints and move historical
   planning/status material into the existing lifecycle taxonomy when touched.
2. Prefer updating authoritative documents over adding overlapping permanent
   documents.
3. Preserve generated references, Chinese mirror, source locks, and resolved
   links.
4. Document cleanup commands and retention policy; do not automatically delete
   backups, databases, screenshots, traces, or user files.

Acceptance criteria:

- A new maintainer can identify authoritative product, architecture, quality,
  release, operations, and security sources from the root README.
- Documentation generation and link checks pass.
- Local/runtime artifacts remain ignored and recoverable according to policy.

Verification:

- `make docs-generate`
- `make docs-check`
- `make harness-static`

## Milestones

### Milestone A: Boundaries and low-risk enablement

- RS-00 baseline and decisions
- RS-03 test taxonomy convention
- RS-10 release-gate alignment
- RS-07 runtime/script boundary, if isolated from active feature work

Exit: structural decisions and gates are executable; no product behavior change.

### Milestone B: Application orchestration boundaries

- RS-01 complete Chat Use Case
- RS-02 shared question/evaluation capabilities

Exit: routers are transport adapters and Agent specialists consume shared
application capabilities while existing behavior remains available.

### Milestone C: Explicit Agent workflow

- RS-04 workflow V2
- RS-05 staged Supervisor retirement

Exit: approved production traffic uses explicit bounded workflow orchestration
with an immediate tested rollback until the observation window closes.

### Milestone D: Sustainable repository internals

- RS-06 persistence slices
- RS-08 tool/operations slices
- RS-09 knowledge/runtime-data ownership
- RS-11 documentation/root hygiene

Exit: the largest maintenance hotspots are reduced without changing the
deployment topology or completed reliability contracts.

## Recommended first delivery slice

The first implementation slice is RS-00 followed by RS-01. It has the highest
leverage because the workflow V2 cannot be introduced safely while HTTP adapters
still own Agent execution and completion. RS-06 must not start with a wholesale
Store split; its first domain slice should begin only after the corresponding
application use case is stable.

Suggested pull-request sequence:

1. Baseline/decision records and new architecture assertions.
2. Chat command/result and Agent-execution ports with compatibility adapter.
3. Non-stream Chat Use Case migration.
4. Streaming Chat Use Case migration and shared failure/cancellation path.
5. Router boundary enforcement and removal of compatibility orchestration.

Each pull request must preserve replay, timeout, cancellation, trace, citations,
budgets, and public response behavior.

## Global verification strategy

During implementation, run focused checks for each task. Before declaring any
repository-wide task complete, run:

```bash
make harness-check
```

External-service PostgreSQL/Redis/Qdrant checks require their documented test
environment. Live model/RAG evaluations are cost-bearing and require explicit
scope and credentials. Missing dependencies must be reported rather than
silently replaced by weaker verification.

## Rollback strategy

- Structural extractions retain compatibility adapters until all callers and
  verification migrate.
- Workflow V2 uses the existing rollout control and retains the old path through
  canary and observation.
- Repository splits do not change database schemas or data locations by default.
- Queue, confirmation, and knowledge-publication correctness mechanisms are not
  rewritten as incidental cleanup.
- Data/artifact relocation requires a separate backup, restore, and operator
  confirmation plan.

## Progress

- [x] Repository-level structure, existing active plans, architecture rules,
      product contracts, quality gates, and completed technical debt reviewed.
- [x] Automated audit/fixer output reviewed in Dry Run mode; no patch applied,
      and false-positive/static-only findings were not promoted blindly.
- [x] Workstreams, dependencies, priorities, acceptance criteria, verification,
      and rollback boundaries defined.
- [x] Documentation generation/check passed and all five deterministic Agent
      evaluation groups passed at `1.0`.
- [x] The static execution-boundary assertion now inspects AST call sites rather
      than raw text. It permits explanatory docstrings while still prohibiting
      real `asyncio.to_thread` calls in API modules; all eight architecture tests
      pass in the focused run.
- [x] RS-00 retained baseline recorded in
      `eval/reports/repository-structure-baseline-2026-08-01.json`, including
      source digests, hotspot sizes, dependency signals, five grouped Agent
      quality rates, and the approved model-routing comparison.
- [x] Chat Use Case responsibilities, ports, error semantics, checkpoint policy,
      migration slices, and rollback boundary accepted in
      `docs/design-docs/chat-use-case-boundary.md`.
- [x] RS-01 implementation refined into review-sized compatibility slices.
- [x] RS-01 slice 1 implemented: transport-neutral execution request/result/port,
      routed compatibility adapter, composition-root wiring, and non-streaming
      Router migration. Routing, timeout, request budget, model accounting, and
      direct `ainvoke` now live outside the HTTP adapter.
- [x] Focused RS-01 slice checks pass: 23 tests covering the execution adapter,
      chat lifecycle, and architecture boundary.
- [x] Repository static gate passes: generated/Chinese documentation is current,
      all five deterministic Agent groups pass at `1.0`, and 23 static,
      architecture, reproducibility, and baseline tests pass.
- [x] Full backend gate passes: Python compilation succeeded and 285 tests
      passed; 2 external-service tests were skipped because their optional
      services were not configured.
- [x] RS-01 slice 2 completed: streaming Agent execution and budget ownership
      use the same application-facing execution port and transport-neutral
      event contract as non-streaming execution.
- [x] RS-01 slice 3 completed: `ChatUseCase` owns evidence/citation projection,
      trace metadata, replay, completion, failure, timeout, and cancellation;
      the Router only maps commands, events, and application errors.
- [x] RS-02 slice 1 completed: versioned question, assessment, and report
      contracts now define one authoritative four-dimension rubric and prompt
      rules reused by formal-interview and chat-specialist adapters. Twenty
      focused interview and multi-Agent tests pass.
- [x] RS-03 taxonomy convention completed without a mass move: `pytest.ini`,
      `tests/README.md`, `docs/testing.md`, and `backend-fast-check` define
      execution cost, dependency markers, and the incremental migration rule.
- [x] RS-07 dependency inversion completed: reusable ingestion and worker job
      processing live under `app`; runtime modules cannot import `scripts`, and
      architecture tests enforce the direction. Command composition remains in
      the worker entry point by design.
- [x] RS-10 packaging alignment completed: release artifacts depend on the
      canonical Harness and the built image is blocked by a fixable high/critical
      Trivy finding before export.
- [x] RS-02 concrete adapter completed: one `ModelInterviewCapabilities`
      instance consumes the versioned request/result contracts and is injected
      into both formal interview application services; legacy callables remain
      as compatibility adapters. Forty focused tests pass.
- [x] RS-04 explicit workflow implemented: single- and multi-intent requests
      execute bounded specialists without a planning or Supervisor call. The
      product contract and focused workflow tests reflect this behavior.
- [x] RS-05 Supervisor retirement completed through the distinct pre-release
      acceptance policy. The fail-closed evidence binds 230 deterministic cases,
      a six-request isolated live cohort, exact identity cleanup, immutable
      current/rollback artifacts, and project-owner post-acceptance approval.
- [x] RS-05 retirement preparation completed: `ChatWorkflowPlanner` is now the
      authoritative rollout and route plan for both invoke and stream, including
      bounded multi-intent routes; the old single-Agent selector cannot silently
      execute only part of such a plan.
- [x] The retained public-production Workflow V2 policy and CLI require a matching
      successful production release ledger, at least 24 hours and 100 completed
      requests, zero zero-tolerance failures, non-regressing quality/completion/
      p95/cost, a verified `off` rollback exercise, and external approval. The
      repository template is tested as insufficient evidence. It remains a
      future public-launch gate and was not relabelled as private-environment data.
- [x] Retirement evidence is provenance-bound: it requires a metrics source,
      stable query IDs, a SHA-256 digest of the redacted quality report, an
      explicit no-user-content assertion, and a second matching production
      ledger entry whose status is `rolled_back` for the rollback exercise.
- [x] Production release preflight is now executable and fail-closed. It rejects
      broad `.env` permissions, missing/placeholder/weak credentials, unsafe
      authentication or schema settings, incomplete optional-provider secrets,
      and a Workflow V2 release without multi-agent execution enabled, while
      emitting only sanitized error codes.
- [x] Workflow V2 production observation is now measurable rather than inferred:
      every completed, failed, or cancelled explicit run exports bounded outcome,
      duration-histogram, and cost counters through Prometheus and OTel; failed
      calls retain their model-run accounting. Versioned fixed PromQL queries
      generate a sanitized operational draft, while quality, security, rollback,
      and external approval deliberately remain impossible for the collector to
      self-approve. Grafana panels and regression alerts consume the same metrics.
- [x] RS-06 persistence decomposition completed by aggregate: chat messages and
      turns, interviews and owner-fenced answers, resumes, interview reviews,
      learning/Agent runs/confirmations/memory, profiles, and administration
      each own their transaction scripts under `app/repositories`. Application
      services use narrow protocols; `storage.py` is a 243-line Engine and
      compatibility composition adapter, down from 4460 lines.
- [x] RS-08 capability decomposition completed: Redis jobs/leases, rate
      limiting, request/product/model metrics, private retrieval, public-search
      provider access, and learning-tool logic have dedicated modules. Stable
      compatibility facades remain bounded at 16 lines (`operations.py`) and
      318 lines (`tools.py`), enforced by architecture tests.
- [x] RS-09 ownership semantics completed without moving data: approved source
      seeds remain confidential by default, `.var/` is ignored, named-volume
      copy-up semantics are documented and tested, and runtime/backup deletion
      still requires explicit operator approval.
- [x] RS-11 documentation/root hygiene conventions completed: root entrypoints
      identify authoritative lifecycle sources and maintenance documentation
      defines read-only inventory, retention, and explicit cleanup approval.
- [x] Crash recovery gap closed for abandoned chat generation: the bounded,
      explicitly confirmed operator command conditionally fails only over-age
      claims, releases session ownership, and fences the old token. Focused
      lifecycle/use-case/architecture tests pass, including late-owner rejection
      and same-key retry under a new claim.
- [x] Project-owned non-production dynamic acceptance is versioned in
      `docs/quality/dynamic-audit.json`. The fault-injection runner passed all
      six state, workflow, interview, knowledge-publication, queue, and security
      scenarios; P0 failures are configured to fail the run.
- [x] Final canonical Harness passed after the recovery change: documentation
      and the 123-document Chinese mirror are current; all five deterministic
      Agent groups scored `1.0`; 28 static/architecture tests, 302 backend tests,
      23 frontend unit tests, bundle budgets, and 28 browser E2E tests passed.
- [x] Optional dependency checks were not counted as success while skipped. The
      local Compose database was found at Alembic `20260730_0017`, upgraded with
      the repository's existing migrations through `20260731_0021`, and both
      PostgreSQL round-trip and Redis lease/dead-letter integration tests then
      passed. No new or duplicate migration was created.
- [x] The canonical Harness passed again after production preflight was added:
      all five deterministic Agent groups scored `1.0`; 28 static/contract
      tests, 318 backend tests, 23 frontend unit tests, type/build/bundle gates,
      and 28 browser E2E tests passed after the observation additions. The
      initial two-worker E2E run had one page-load timing failure; that exact
      specification passed alone and the full 28-test suite passed with one
      worker, so it was not treated as a product regression. Two explicitly marked external-service
      backend tests remained skipped in the default suite; their PostgreSQL and
      Redis variants had already passed against the local Compose services.
- [x] The first approved Workflow V2 production activation exercised the real
      stop and rollback path. A multi-intent smoke turn failed closed with
      `ModelBudgetExceeded` after the fifth shared chat-model call; the stage was
      returned to `off`, health/readiness and deterministic Supervisor fallback
      passed, the isolated smoke account was removed, and release
      `production-workflow-v2-20260802-41ae64d192ab-r2` was recorded as
      `rolled_back` with no user content in its evidence.
- [x] The production telemetry gap found during that drill was operational, not
      a source regression: the running Collector predated the configured metrics
      pipeline. Recreating only the Collector loaded the existing configuration,
      after which both OTLP `/v1/traces` and `/v1/metrics` accepted payloads.
- [x] Workflow V2 retry hardening completed: explicit routes receive a
      bounded per-specialist model-call allowance while retaining shared token
      and cost ceilings, and the BM25 cache is persisted and prewarmed so app
      replacement does not repeat a request-path model download.
- [x] Production configuration can no longer leak into the local Harness.
      Pytest and Playwright now clear API/model credentials, force rollout off,
      disable OTel export, and use isolated SQLite state before importing or
      starting the application. This was verified by the 23 previously affected
      backend tests and all 28 browser scenarios without a live model call.
- [x] The hardened candidate passed the canonical Harness (320 backend tests,
      2 explicit external-service skips, 23 frontend unit tests, and 28 browser
      scenarios). App image `sha256:af847cd1f86457d43d102729416a789c168dfe6f2e26648265a2293711fe3f6a`
      and worker image `sha256:ee6e2e3c82b3e1892a28b612b2f543ea26056c01c462e88b8e999a5306af6add`
      contain matching `rag.py` and `config.py` source digests. Socket-free,
      tar-input Trivy scans found zero fixable HIGH/CRITICAL findings in both.
- [x] A stale r3 candidate was detected before observation when its in-image
      `rag.py`/`config.py` digests did not match the concurrently completed
      hardening sources. Production was returned to `off`, health and
      authenticated readiness passed, and r3 was recorded as `rolled_back`
      instead of being accepted as observation evidence.
- [x] Hardened release
      `production-workflow-v2-20260802-af847cd1f864-r4` passed production
      preflight, staged app/worker replacement, Alembic head verification,
      persistent BM25 warmup and post-restart cache reuse. Its isolated real
      `knowledge+planner` smoke completed in 65.201 seconds, incremented the
      Workflow V2 completion metric by one, produced two-model provenance, and
      returned a non-empty answer. The exact smoke account, revoked tokens,
      conversation, messages, turn, and trace were then verified absent.
- [x] A post-release completion audit found that independent multi-intent
      specialists were still awaited serially despite the RS-04 plan. Invoke
      and stream now start sibling routes concurrently, preserve route-order
      composition, share the bounded request budget, and cancel unfinished
      siblings after a route failure. Twenty-five focused chat tests and the
      canonical Harness passed with 323 backend tests, 2 explicit
      external-service skips, 23 frontend unit tests, and 28 browser scenarios.
- [x] The r4 observation cannot authorize retirement of the corrected
      concurrent implementation because its immutable images contain the prior
      serial executor. It was superseded by the approved pre-release acceptance
      route rather than being misrepresented as valid retirement evidence.
- [x] The concurrent r5 candidate passed production preflight, the canonical
      Harness, in-image source digest verification, and socket-free Trivy scans
      with zero fixable HIGH/CRITICAL findings. App and Worker both use image
      `sha256:3b6a312412e37fe94f525a9a98d08702c9a9ff730dbf73a82e18fd4469b8391d`;
      `chat_agent_executor.py` is bound to digest
      `4f396f9905e0c3b6e7e371d3af546d496c421d128feadde961f798556b864c6a`.
- [x] The first concurrent-r5 replacement remained correctly stopped because
      fresh production approval was absent. That historical attempt was closed:
      deployment attempt was stopped by the approval gate before any container
      replacement. `.env`, runtime stage, default image tags, and the online r4
      app/Worker were restored and verified unchanged; health and authenticated
      readiness remained 200. Release
      `production-workflow-v2-concurrent-20260802-3b6a312412e3-r5` was closed as
      `failed` with `deployment=not-started-approval-required` rather than left
      in a misleading `deploying` state.
- [x] The retirement evidence audit found a second apples-to-oranges gap before
      approval: the collector used the historical deterministic direct-routing
      canary's 850 ms as the baseline for full live production workflow latency.
      The retained Supervisor and Workflow V2 now export the same bounded
      outcome, duration, and cost metrics. The collector and fail-closed gate
      require separate Supervisor and V2 production windows, each at least 24
      hours and 100 completed requests, with all eight stable query IDs.
- [x] The canonical Harness passed after the dual-window evidence correction:
      all five deterministic Agent groups scored `1.0`; 28 static/architecture
      tests, 333 backend tests, 23 frontend unit tests, type/build/bundle gates,
      and 28 browser E2E tests passed. Two explicitly marked external-service
      backend tests remained skipped in the default suite. The initial
      two-worker browser run had one page-load timing failure; that exact test
      passed alone and the complete 28-test browser suite passed with one
      worker, so the failure was recorded as an isolated timing flake rather
      than product evidence.
- [x] The dual-window production evidence was correctly rejected as infeasible
      for the unreleased, low-traffic environment. It remains unchanged as the
      public-launch policy; synthetic traffic was not presented as real traffic.
- [x] The replacement r5 pre-release candidate was built, scanned, deployed and
      accepted. Its immutable current/rollback artifacts and successful/rolled-
      back ledgers are bound into the pre-release evidence.
- [x] Post-window review preparation is executable and non-approving. It accepts
      only a passing grouped quality report with zero zero-tolerance failures,
      binds its byte-level SHA-256 and the exact rollback release ID into the
      Prometheus draft, asserts that no user content is present, and resets all
      approval fields to `pending`. Thirteen focused observation/retirement tests
      pass; an external approver must still inspect and sign the final evidence.
- [x] RS-05 completed through the distinct fail-closed pre-release policy. The
      owner-approved evidence passed against the production ledger; runtime
      Supervisor prompts, selectors and tool paths were removed. The final r6
      app/worker image
      `sha256:6b1432d0a26f8943da46d087ffa2a68851259ebac5e5eabde9d0153a20c416a5`
      passed in-image source/topology checks and pinned Trivy scans. Release
      `production-workflow-v2-supervisor-free-20260802-6b1432d0-r6` succeeded
      with health/readiness 200, explicit Workflow V2 topology, a real
      evaluator+interviewer smoke and exact identity cleanup verified at zero.

## Completion

All RS workstreams and their mandatory repository, image, deployment and
cleanup gates are complete. The historical dual-window modules and queries
remain as the future public-production launch policy. Runtime rollback now
means loading the digest-verified previous app and worker artifacts and
recording a new release-ledger transition.
