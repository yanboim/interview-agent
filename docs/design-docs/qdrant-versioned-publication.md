# Qdrant versioned knowledge publication

## Context

The original ingestion process deleted `QDRANT_COLLECTION` before uploading its
replacement and ran quality evaluation only afterward. A failed upload or
regression could therefore remove the last known-good knowledge base.

## Decision

Use immutable versioned physical collections and a stable serving alias:

```text
legacy fallback: interview_knowledge
serving alias:   interview_knowledge_current
versions:        interview_knowledge__v_<UTC timestamp>_<job suffix>
```

Readers resolve the alias on each logical retrieval/cache lookup. If the alias
does not yet exist, they use the legacy collection. Publication creates and
validates a version, then atomically replaces the alias in one Qdrant alias
update request.

Redis holds a token-owned publication lock with a bounded TTL. Lock release uses
compare-and-delete semantics so an expired publisher cannot release a newer
publisher's lock.

Cache keys include the physical collection name behind the alias. Alias
switching therefore changes the cache namespace without scanning or deleting
unrelated Redis keys.

## Failure behavior

- Credential failure: no collection is created.
- Upload or structural validation failure: delete only the new candidate.
- Regression failure: delete only the new candidate.
- Alias switch failure: delete only the unpublished candidate; the previous
  alias remains authoritative because Qdrant applies an alias operation list
  atomically.
- Lock contention: reject the publication with a conflict-style error.
- Redis unavailable while configured: reject publication rather than allow two
  publishers.
- Redis not configured: a process-local lock supports local development only.

## Rollback

Rollback accepts only an existing collection whose name matches the configured
version prefix. It atomically points the serving alias to that collection.
Rollback never deletes the version being left.

## Consequences

- Historical versions consume Qdrant storage until retention is implemented.
- Alias resolution adds a lightweight Qdrant metadata request before cache
  lookup. Correct cache versioning is prioritized over premature caching of
  alias metadata.
- Multiple application processes do not need an in-process vector-store cache
  invalidation broadcast because their resolved physical target changes when
  the alias changes.
