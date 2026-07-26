# Synchronous persistence boundary

## Context

The application uses synchronous SQLAlchemy Core with both SQLite and
PostgreSQL. FastAPI adapters currently decide individually when to call
`asyncio.to_thread`, while `ConversationStore` serializes nearly every
operation through one `threading.RLock`. The thread switching is duplicated,
and the lock provides only single-process serialization even though production
correctness must hold across replicas.

## Decision

Retain synchronous SQLAlchemy Core and use this execution model:

```text
async API adapter
  -> SyncExecutor.run(application service or Store transaction script)
      -> synchronous SQLAlchemy Engine
          -> one engine.begin() per mutation
          -> one engine.connect() per read
```

`SyncExecutor` is the only API-layer bridge to the worker thread pool. Store
methods remain synchronous transaction scripts: their transaction begins and
ends inside the method. Application workflows with external model calls use
short durable claim and completion transactions, leaving no connection or
transaction open during network I/O.

Conditional updates, unique constraints, foreign keys, idempotency keys, and
claim-owner tokens define concurrency correctness. A process lock may protect
one-time local schema initialization, but it must not surround business reads
or writes and is not part of any use-case correctness argument.

## Consequences

- The event loop does not execute blocking database work.
- Transaction ownership is visible at the Store method boundary.
- Concurrent tests exercise database behavior instead of Python serialization.
- PostgreSQL remains the production concurrency authority; SQLite remains a
  supported local/test adapter with its native write serialization.
- Moving to async SQLAlchemy later would replace the executor and repository
  implementation, not alter domain transition semantics.
