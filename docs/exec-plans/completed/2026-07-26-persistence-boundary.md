# Persistence execution boundary

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-005
- Product contract: `persistence-execution-boundary`

## Objective

Keep SQLAlchemy Core synchronous while making its async integration and
transaction ownership explicit. Route adapters use one executor for blocking
application/infrastructure calls, Store mutation methods own complete database
transactions, and database constraints/conditional writes—not a Python
process lock—protect business transitions.

## Non-goals

- Convert SQLAlchemy, drivers, or repository methods to async.
- Introduce an ORM session abstraction.
- Hold a database transaction open across an LLM or network call.
- Change public HTTP behavior or database schema.
- Replace Redis/Qdrant concurrency mechanisms.

## Acceptance criteria

- One documented synchronous SQLAlchemy model is used throughout the app.
- API routers contain no direct `asyncio.to_thread` calls.
- A single executor boundary runs synchronous use cases away from the event
  loop and preserves keyword arguments.
- Each Store mutation opens and commits one complete transaction script.
- Chat/interview claims remain separate short transactions around model calls.
- `ConversationStore` business reads and writes do not depend on its process
  `RLock`.
- Concurrent chat and interview claim tests pass without a Store business lock.
- Architecture tests enforce the execution boundary and lock rule.
- Existing endpoint behavior remains compatible and `make harness-check`
  passes.

## Implementation steps

1. Add the shared synchronous-call executor and expose it in `ApiRuntime`.
2. Migrate middleware and routers from direct thread dispatch to the executor.
3. Remove Store business-operation locking while retaining only narrowly scoped
   schema-initialization synchronization if required.
4. Strengthen concurrent claim tests and architecture checks.
5. Update architecture, product contract, and technical-debt status.

## Progress

- [x] Existing engine, transaction, thread-dispatch, and lock usage inventoried.
- [x] Shared execution boundary implemented.
- [x] API adapters migrated.
- [x] Store business lock removed.
- [x] Focused concurrency and architecture checks pass.
- [x] Full Harness gate passes: 11 static checks; 124 backend tests passed with
      1 external-service test skipped; 10 frontend unit tests; type-check,
      production build, bundle budgets, and 10 Playwright scenarios passed.

## Decisions and findings

- Retained synchronous SQLAlchemy Core. The migration cost and driver changes
  of async SQLAlchemy were unnecessary to establish a clear correctness
  boundary.
- `SyncExecutor` is the only `asyncio.to_thread` call site used by the API
  layer. It accepts complete synchronous use cases and preserves keyword
  arguments through a partial.
- Removed `ConversationStore`'s broad `RLock` from all business reads and
  writes. A narrow initialization lock remains only around optional local
  `metadata.create_all`.
- Existing concurrency tests already use independent Store/Engine instances
  against the same database for chat and interview claims. They pass without
  Python serialization, exercising conditional database transitions directly.
- Transactions remain deliberately short around chat/interview claim and
  completion. Model calls occur between them and never retain a connection.

## Rollback

No migration or persisted-data change is involved. Rollback restores direct
thread dispatch and the Store lock; database transactions and schema remain
compatible.
