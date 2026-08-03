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
  |---- PostgreSQL or SQLite: users, sessions, resumes, reviews, learning, audits
  |---- Redis: shared rate limits, RAG cache, background jobs
  |---- Qdrant: versioned private knowledge index
  |---- User file volume: avatars, resumes, temporary review audio
  |---- GLM API: chat, interview questions, scoring, optional reranking
  |---- Transcription API: optional consent-gated audio transcription
  `---- Worker: knowledge, resume, transcription, and review jobs
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

Current application services:

```text
app/application/chat_service.py
app/application/interview_service.py
app/application/resume_service.py
app/application/interview_review_service.py
```

New complex behavior should continue moving toward this boundary rather than
placing orchestration in API routers or `app/main.py`.

Knowledge publication is currently coordinated by the ingestion/worker adapters
and `app/knowledge_publication.py`. Introduce a dedicated
`app/application/knowledge_service.py` only when an additional API use case
needs an application-facing boundary; it is not present today.

### Domain policy

Contains deterministic calculations and state-transition rules. It must remain
independent of FastAPI, SQLAlchemy, Redis, Qdrant, HTTP clients, and LLM SDKs.

Current examples include `app/learning.py`, `app/chunks.py`, and
`app/evaluation.py`. Their purity is enforced by architecture tests.

### Infrastructure

Owns SQLAlchemy, Redis, Qdrant, external HTTP, telemetry, and model provider
details. Infrastructure may implement application-facing interfaces but must
not import the API composition root.

Current persistence implementations are composed from aggregate slices in
`app/repositories/`; `app/storage.py` retains the shared Engine, schema
initialization, system counts, user administration, and compatibility class.
Redis jobs/leases, rate limiting, request metrics, private retrieval, public
search, and learning-tool logic live in capability-specific modules while
`app/operations.py` and `app/tools.py` preserve stable compatibility exports.
Further namespace grouping remains incremental work, not a flag-day rewrite.

## Correctness boundaries

### User data

The server-resolved authenticated identity is authoritative. Every user-owned
query and mutation includes `user_id`; a client-supplied ID is never sufficient
authorization.

Administrator observability has three distinct persistence concerns:

- `audit_events` records who performed an API action, its sanitized target,
  request ID, outcome, and timing;
- canonical chat/interview tables remain the only source for exact user input
  and system output;
- `execution_traces` and correlated tool audits record model/tool stages and
  safe metadata without copying prompts, credentials, or private knowledge
  text.

Cross-user interaction reads are administrator-only and are themselves captured
by request auditing.

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
turn for retry. A process crash while `generating` requires the explicit
`scripts.recover_stale_chat_turns` operator command. Recovery conditionally
changes only an over-age owner claim to `failed`, releases the session, and
invalidates its token so a late prior owner cannot commit. Automatic time-based
takeover remains prohibited because an in-flight model call cannot itself be
cancelled or leased safely.

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

The implementation uses versioned physical collections, validates candidates,
switches the serving alias atomically, versions cache keys by physical target,
and retains the previous version for rollback. Deleting the serving collection
before validation remains prohibited.

### User-sensitive files and long-running analysis

Avatars, resumes, and temporary interview audio use server-generated storage
keys and authenticated download paths; user files are never served as static
assets or placed in Qdrant. The API and Worker share the configured persistent
user-file volume. Database rows are authoritative for ownership and lifecycle,
while file cleanup is idempotent.

Resume analysis and interview review use explicit durable resource states,
owner-fenced background jobs, bounded model/transcription calls, and
optimistic revisions for editable drafts and transcripts. Audio leaves the
system only when transcription is enabled and the user explicitly confirms
external processing. Successfully persisted transcripts trigger audio
deletion.

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

`app/agent_context_service.py` owns the separate immutable per-turn agent
context snapshot. It combines server-resolved identity and profile data with
only confirmed, owner-scoped coaching memory, current capability weaknesses,
due learning tasks, and the bounded conversation view. Proposed/rejected or
stale source-derived memories never enter the snapshot. Specialist calls
receive one versioned `DelegationEnvelope` with this compact snapshot and
correlation identifiers; the full chat transcript is not copied into every
delegation. Memory lifecycle operations remain explicit product/API commands,
and a correction returns the memory to `proposed` until the owner confirms it
again.

Durable multi-step Agent actions use `app/application/agent_run_service.py`
and the application-owned `agent_runs`/`agent_steps` records as their business
source of truth. Stable input digests and step idempotency keys bind retries to
the original command. Step claims are conditional and owner-fenced; command
effects, replay results, and terminal step/run state commit atomically, while
any future model or tool calls remain outside database transactions. SSE
exposes lifecycle events only, and administrator inspection omits user-owned
input, proposal, and result bodies. LangGraph remains an in-process
orchestration detail rather than durable product state.

## Deployment and lifecycle

- Alembic owns production schema evolution; runtime `create_all` is for local
  and isolated tests only.
- Migrations run before the application accepts traffic.
- `/health` is a liveness signal; `/ready` verifies required dependencies.
- The worker uses owner-fenced Redis claims, job-lease heartbeat,
  acknowledgement, bounded retry, crash recovery, and terminal failure state.
  An independent process heartbeat with a bounded Redis TTL remains active
  while the Worker is idle or processing and supplies the administrator
  resource center's live Worker signal.
- API and Worker deployments that enable resume or review processing mount the
  same persistent user-file volume. Backup and restore treat relational rows
  and that volume as one recovery set.
- Verified Canary and production outcomes are written to an idempotent
  deployment-release ledger by the operator-side deployment process. Git
  history is not treated as proof that a version reached an environment, and
  product users cannot access this administrator read model.
- Compose is the developer reference environment. Each worktree derives a
  stable `COMPOSE_PROJECT_NAME` and host-port block; Compose project names
  isolate its containers, network, and named volumes.

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
