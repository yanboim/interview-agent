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

Current location: mostly `app/main.py`.

### Application services

Coordinate a use case and its transaction/concurrency boundary, such as
submitting an interview answer or generating a chat turn. They depend on
repository and model interfaces rather than global clients.

Target modules:

```text
app/application/chat_service.py
app/application/interview_service.py
app/application/knowledge_service.py
```

These modules do not yet exist. New complex behavior should move toward this
boundary rather than enlarge `app/main.py`.

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

### Chat and interview turns

Each logical turn should have a durable identity and explicit lifecycle. The
target lifecycle is:

```text
pending -> generating -> completed
                    `-> failed or cancelled
```

Concurrent submissions for the same pending turn must not cause duplicate
model charges or duplicate successor turns. This remains tracked debt until the
current storage schema implements it.

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

- `app/main.py` hosts most routes and application orchestration.
- Sync SQLAlchemy calls are dispatched manually from async routes.
- Several service/client instances are module-level globals.
- Knowledge ingestion currently replaces the serving Qdrant collection
  in-place.
- Chat and interview commands lack complete idempotency/concurrency state.

Exceptions must be reduced or held steady. New code should not create additional
instances of these patterns without an accepted design record.
