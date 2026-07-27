# Atomic knowledge publication

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-001
- Product contract: `atomic-knowledge-publication`

## Objective

Replace destructive in-place Qdrant ingestion with a versioned publication
workflow that preserves the serving knowledge base until a candidate has passed
validation, switches traffic atomically, isolates caches by version, prevents
concurrent publishers, and supports rollback.

## Non-goals

- Replace the Redis `BLPOP` worker with a durable queue.
- Refactor all administration routes out of `app/main.py`.
- Change document chunking, embeddings, or retrieval ranking behavior.
- Automatically delete historical collections without an explicit retention
  policy.

## Compatibility decision

`QDRANT_COLLECTION` remains the legacy physical collection name and version
prefix. A distinct stable alias, `QDRANT_COLLECTION_ALIAS`, becomes the serving
target. Before an alias exists, readers fall back to the legacy collection.
This permits an existing deployment to upgrade without deleting or renaming its
current collection.

## Acceptance criteria

- A candidate is written to a unique versioned collection.
- Structural validation and configured RAG regression run against the candidate
  before publication.
- Failed builds remove only their unpublished candidate and leave the serving
  alias or legacy collection unchanged.
- Alias replacement uses one Qdrant alias update request.
- Redis locking permits one publisher at a time and releases only the owning
  token.
- RAG cache keys include the physical collection version behind the alias.
- The previous serving collection remains available and can be selected by an
  authenticated administrator rollback endpoint.
- Readiness and runtime checks understand the alias/legacy fallback.
- Unit tests cover initial publication, replacement, validation failure,
  contention, cache versioning, and rollback.
- `make harness-check` passes.

## Implementation steps

1. Add alias, lock TTL, and retained-version configuration.
2. Add a knowledge publication service containing Qdrant alias and version
   operations.
3. Make retrieval resolve the serving target and physical version dynamically.
4. Rewrite ingestion to build, validate, evaluate, and publish candidates.
5. Add administrator status and rollback endpoints and pass job IDs into
   background ingestion.
6. Add tests and update the product contract, architecture, operations
   documentation, and debt tracker.

## Progress

- [x] Existing ingestion, retrieval cache, Worker, admin routes, and local
      Qdrant client API inspected.
- [x] Implementation complete.
- [x] Focused tests pass: 40 tests covering publication, retrieval, locks,
      administrator routes, and architecture.
- [x] Full backend suite passes: 100 passed, 1 skipped.
- [x] Full Harness gate passes: static contracts 6 passed; backend 100 passed
      and 1 skipped; frontend type-check, 9 unit tests, production build, and
      bundle budgets passed; Playwright 10 passed.

## Verification notes

The first sandboxed Playwright launch timed out while probing the already
started localhost server because local socket access was denied. Re-running the
same repository E2E command with localhost access completed all 10 tests.

## Rollback

Code rollback remains compatible because the legacy `QDRANT_COLLECTION`
collection is never renamed. Operational rollback switches the stable alias to
one of the retained versioned collections. No historical collection is deleted
as part of rollback.
