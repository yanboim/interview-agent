# Architecture

## Purpose

Interview Agent is a modular monolith serving a Vue web application and a
FastAPI API. It combines authenticated user data, interview workflows, learning
plans, an LLM-based coach, and a private Qdrant knowledge base.

The current deployment unit is intentionally one application plus one
background worker. Network microservices are not a target until transaction and
module boundaries are explicit inside the monolith.

## Runtime context

```text
Browser
  |
  v
FastAPI API / static frontend
  |---- PostgreSQL or SQLite: users, sessions, interviews, learning, audits
  |---- Redis: shared rate limits, RAG cache, background jobs
  |---- Qdrant: versioned private knowledge index
  |---- GLM API: chat, interview questions, scoring, optional reranking
  `---- Worker: long-running knowledge ingestion
```

Prometheus, Grafana, and OpenTelemetry observe the application but are not part
of the request's correctness boundary.

## Source-of-truth hierarchy

1. Executable tests and database constraints.
2. `docs/product-specs/feature-contract.json`.
3. This architecture document and accepted design records.
4. Operational documentation in `README.md`.
5. Historical plans and evaluation reports.

When sources disagree, establish actual behavior with an executable check and
update the stale source in the same change.

## Logical layers

The target dependency direction is:

```text
API adapters
    -> application services
        -> domain policy and calculations
            <- infrastructure implementations
```

### API adapters

Own HTTP validation, authentication dependencies, status codes, and response
serialization. They do not own interview transitions, prompt construction, SQL
queries, or retry policy.

Current location:

```text
app/api/runtime.py
app/api/schemas.py
app/api/security.py
app/api/routers/
```

`app/main.py` is the composition root: it constructs dependencies, installs
middleware and static routes, and registers domain routers.

### Application services

Coordinate a use case and its transaction/concurrency boundary, such as
submitting an interview answer or generating a chat turn. They depend on
repository and model interfaces rather than global clients.

Current and target modules:

```text
app/application/chat_service.py
app/application/interview_service.py
app/application/knowledge_service.py
```

New complex behavior should continue moving toward this boundary rather than
placing orchestration in API routers or `app/main.py`.

### Domain policy

Contains deterministic calculations and state-transition rules. It must remain
independent of FastAPI, SQLAlchemy, Redis, Qdrant, HTTP clients, and LLM SDKs.

Current examples include `app/learning.py`, `app/chunks.py`, and
`app/evaluation.py`. Their purity is enforced by architecture tests.

### Infrastructure

Owns SQLAlchemy, Redis, Qdrant, external HTTP, telemetry, and model provider
details. Infrastructure may implement application-facing interfaces but must
not import the API composition root.

Current implementations are still organized as flat modules under `app/`.
Moving them into `app/infrastructure/` is incremental work, not a flag-day
rewrite.

## Correctness boundaries

### User data

The server-resolved authenticated identity is authoritative. Every user-owned
query and mutation includes `user_id`; a client-supplied ID is never sufficient
authorization.

### Database writes

A single business transition should commit atomically. Retriable commands need
an idempotency key or an optimistic concurrency condition. Python process locks
are not a correctness mechanism in a multi-instance deployment.

Persistence uses synchronous SQLAlchemy Core. API adapters dispatch blocking
use cases through the shared `SyncExecutor`; they do not call
`asyncio.to_thread` individually. A `ConversationStore` mutation is a
transaction script and owns one `engine.begin()` boundary, while reads own one
`engine.connect()` boundary. External model and network calls never run inside
those database transactions.

Business concurrency is enforced by conditional updates, unique constraints,
foreign keys, idempotency keys, and owner tokens. The Store's only local lock
guards optional schema initialization and is not part of business correctness.

### Chat and interview turns

Each logical turn should have a durable identity and explicit lifecycle. The
target lifecycle is:

```text
pending -> generating -> completed
                    `-> failed or cancelled
```

Initial interview-answer and chat submission implement this lifecycle using
durable turn IDs, client idempotency keys, database conditional claims,
claim-owner tokens, and stored response replay.

Chat additionally serializes generation per session and materializes its user
and assistant history messages together only after completion. Provider failure
or stream cancellation releases the session and preserves the failed/cancelled
turn for retry. A process crash while `generating` still requires explicit
operator recovery; automatic lease takeover is prohibited until model-call
fencing can prevent a slow prior owner from resuming.

### Knowledge publication

Knowledge ingestion is a release process:

```text
build versioned collection
  -> validate structure
  -> run regression gate
  -> atomically switch alias
  -> invalidate versioned cache
  -> retain previous version for rollback
```

Deleting the serving collection before validation is prohibited for new
implementation work and tracked as an existing P0 issue.

### Model calls

Provider calls require bounded timeout/retry behavior, metrics, safe error
mapping, and token/cost accounting. Prompts and structured-output schemas are
versioned behavior. Product code must not rely on unvalidated free-form JSON
when a structured-output facility is available.

`app/model_gateway.py` is the sole external chat/embedding construction point.
It applies timeout, retry, concurrency, input/output budget, safe-error,
latency/error metric, and token-accounting policy. Agent graphs and application
services own prompts and orchestration, not provider transport behavior.

Chat model input is a bounded derived view; `messages` remains the immutable
history source of truth. `app/chat_context.py` plans a provider-independent
window containing a durable summary, recent completed messages, and the current
request. The conversation summary marker advances in the same transaction that
claims the chat turn, so failed/retried calls cannot duplicate compaction.

## Deployment and lifecycle

- Alembic owns production schema evolution; runtime `create_all` is for local
  and isolated tests only.
- Migrations run before the application accepts traffic.
- `/health` is a liveness signal; `/ready` verifies required dependencies.
- The worker must use durable job semantics before jobs become business
  critical.
- Compose is the developer reference environment. Per-worktree isolation is a
  target; fixed container names and ports are tracked debt.

## Verification architecture

- Unit tests verify deterministic domain and adapter behavior.
- Architecture tests mechanically enforce dependency rules and repository
  contracts.
- Migration tests verify schema creation and revision continuity.
- Playwright tests verify critical browser behavior.
- RAG and routing evaluation datasets detect model/retrieval regressions.
- `make harness-check` is the canonical local verification entry point.

## Known exceptions

The following are documented legacy constraints, not preferred patterns:

- Several service/client instances are module-level globals.

Exceptions must be reduced or held steady. New code should not create additional
instances of these patterns without an accepted design record.
