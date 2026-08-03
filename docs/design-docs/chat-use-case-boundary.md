# Chat Use Case boundary

## Status

Accepted for incremental implementation on 2026-08-01. This decision defines
the RS-01 extraction boundary; it does not enable Workflow V2 by itself.

## Context

The durable chat-turn lifecycle is already application-owned, but the HTTP
adapter still coordinates route selection, model-purpose selection, request
budget scope, Agent invocation, tool-result evidence extraction, citation
projection, trace recording, completion, timeout, failure, and cancellation.
The ordinary and streaming endpoints consequently duplicate part of the same
business flow and can evolve differently.

The extraction must preserve the existing correctness boundaries:

- authenticated ownership is server-resolved;
- one durable turn is claimed by idempotency key and owner token;
- external model and network calls stay outside database transactions;
- completion atomically materializes the final messages and metadata;
- timeout, provider failure, and disconnect release the session safely;
- Workflow V2 sibling cancellation is bounded; an uncooperative provider task
  cannot keep the durable turn lock open after the parent timeout;
- completed requests replay their stored result without another model call;
- budgets, evidence isolation, confirmations, provenance, metrics, and safe
  errors remain enforced.

## Decision

Introduce one application-owned Chat Use Case that coordinates the complete
logical turn. HTTP adapters become protocol translators and do not select or
invoke Agents directly.

### HTTP adapter responsibilities

- validate HTTP schemas, headers, authentication, and authorization;
- translate a request into `ChatCommand`;
- choose ordinary JSON or streaming transport;
- serialize application events/results into the public response protocol;
- translate stable application errors into HTTP status and safe response text;
- propagate a client-disconnect cancellation signal.

### Application use-case responsibilities

- claim or replay the durable chat turn;
- build the server-owned bounded context snapshot;
- select the admitted route and model purpose through an injected policy;
- open and report the request-scoped execution budget;
- invoke the Agent execution port with bounded timeout/cancellation;
- normalize evidence and project citation metadata;
- record safe execution traces and product/model metrics;
- complete, fail, or cancel the claimed turn with its owner token;
- return transport-neutral result or lifecycle events.

### Ports

Use narrow ports only at volatile or side-effecting boundaries:

- `ChatTurnRepository` for claim/replay/complete/terminate transitions;
- `ChatAgentExecutor` for admitted Agent/model execution;
- `ChatTraceRecorder` for safe correlated execution traces;
- an injectable clock/identifier only where deterministic tests need one.

Pure evidence/citation transformations remain ordinary application functions.
They should not become infrastructure ports merely to increase interface count.

The existing `ConversationStore`, Agent assembly, and trace persistence act as
compatibility adapters during migration. No database migration is required.

## Execution sequence

```text
HTTP adapter
  -> ChatUseCase.execute(command, cancellation)
       -> claim/replay durable turn
       -> establish identity and bounded context
       -> select admitted route and budget
       -> invoke ChatAgentExecutor outside database transaction
       -> normalize evidence and citations
       -> complete durable turn and record safe trace
  <- ChatResult or stable application error
```

The streaming variant uses the same claim, execution policy, metadata, and
terminal transition. It may expose transport-neutral delta/lifecycle events,
but NDJSON/SSE formatting stays in the HTTP adapter. A disconnect requests
cancellation; the use case owns the durable `cancelled` transition.

## Error semantics

Application errors are stable categories rather than raw provider or database
exceptions:

- invalid/current-message budget exceeded;
- idempotency input conflict;
- turn already in progress or session busy;
- model temporarily unavailable or execution budget exhausted;
- execution timeout;
- cancelled by client;
- terminal internal failure.

Raw exception text is retained only in safe server-side logs/traces. The HTTP
adapter maps categories to the existing public response behavior.

## Workflow and checkpoint policy

RS-01 is a behavior-preserving extraction. It keeps the current admitted Agent
path. Explicit guard/router/specialist/verifier/composer stages belong to RS-04.

Ordinary chat does not gain a persistent LangGraph checkpointer by default. The
durable chat turn, owner fencing, canonical messages, metadata, and safe trace
remain the product state. A later workflow may persist additional checkpoints
only after defining model-call replay, stale-owner fencing, side-effect
idempotency, privacy, and retention semantics.

## Alternatives rejected

### Keep orchestration in both routers

Rejected because ordinary and streaming behavior can drift and transport code
continues to own model and persistence policy.

### Move the current router body into one large service unchanged

Rejected because it would hide HTTP objects and response formatting inside the
application layer rather than create a transport-neutral use case.

### Introduce Workflow V2 in the same change

Rejected because extraction and behavior replacement would remove a trustworthy
comparison boundary and make rollback harder.

### Persist every Agent node immediately

Rejected because external model calls are not exactly-once and automatic
takeover is unsafe without explicit fencing and side-effect semantics.

## Migration

1. Add command/result/error contracts and compatibility execution adapters.
2. Move the non-streaming endpoint behind the use case without behavior change.
3. Move streaming execution to the same use case and shared terminal handling.
4. Add architecture assertions that API routers cannot invoke Agents/models.
5. Remove compatibility orchestration after focused and repository gates pass.

Each step remains independently revertible and requires no schema migration.

## Verification

- chat lifecycle, replay, timeout, budget, provider failure, and cancellation;
- ordinary and streaming metadata/citation parity;
- cross-user and idempotency negative cases;
- model call remains outside repository transactions;
- architecture rule preventing Agent/model invocation in API routers;
- deterministic Agent quality and model-routing non-regression;
- `make harness-check` before RS-01 is complete.
