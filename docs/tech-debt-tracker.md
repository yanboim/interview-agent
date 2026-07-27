# Technical debt tracker

This is the prioritized architectural debt register. Product bugs should remain
in the normal issue tracker unless they represent a recurring system boundary
problem.

| ID | Priority | Area | Problem | Exit criteria | Status |
|---|---|---|---|---|---|
| TD-001 | P0 | Knowledge | Ingestion deletes the serving Qdrant collection before the replacement passes regression evaluation. | Build a versioned collection, validate it, switch an alias atomically, version/invalidate cache, and retain a rollback version. | Completed 2026-07-26 |
| TD-002 | P0 | Interviews | Concurrent/retried answer submissions can score or advance the same turn more than once. | Durable turn identity, idempotency key, conditional state transition, and concurrency tests exist. | Completed 2026-07-26 |
| TD-003 | P1 | Chat | Chat writes the user message before generation and lacks a durable per-turn lifecycle. | Pending/generating/completed/failed state, retry semantics, session ordering, and disconnect recovery are tested. | Completed 2026-07-26 |
| TD-004 | P1 | API architecture | `app/main.py` combines transport, DTOs, orchestration, administration, files, and lifecycle setup and currently exceeds 2,000 lines. | Domain routers call application services; the composition root contains wiring and middleware rather than business flows. | Completed 2026-07-26 |
| TD-005 | P1 | Persistence | Sync SQLAlchemy plus scattered `asyncio.to_thread` and process-local locks obscures transaction and concurrency behavior. | One documented sync or async database model, request/use-case transaction ownership, and no correctness dependence on process locks. | Completed 2026-07-26 |
| TD-006 | P1 | Jobs | Redis `BLPOP` jobs have no acknowledgement, retry, lease, dead-letter, or idempotency semantics. | Durable claim/ack/retry flow with crash-recovery tests. | Completed 2026-07-26 |
| TD-007 | P1 | LLM | Provider calls lack a single gateway for timeout, retry, concurrency, budget, and error policy. | All model calls use one policy-bearing gateway and expose latency/token/error metrics. | Completed 2026-07-26 |
| TD-008 | P2 | Context | Chat sends unbounded conversation history to the model. | Token-budgeted recent history plus durable summary and truncation tests. | Completed 2026-07-26 |
| TD-009 | P2 | Developer environment | Fixed Compose names, ports, and shared resource names prevent isolated per-worktree stacks. | A generated project/resource suffix allows two worktrees to run concurrently. | Completed 2026-07-26 |
| TD-010 | P2 | Reproducibility | Broad Python lower bounds and a `latest` Qdrant image permit non-reproducible environments. | A reviewed lock/update workflow and immutable production image versions are enforced in CI. | Completed 2026-07-26 |
| TD-011 | P2 | Frontend toolchain | The developer dependency audit still reports six Vite/vue-tsc-related warnings; these packages are build-time only and do not enter production runtime dependencies. | Upgrade the related major versions in one reviewed change, update the lockfile, and pass `make harness-check` without the six warnings. | Completed 2026-07-26 |
