# Backend test taxonomy

The backend suite remains path-compatible while it moves incrementally toward
clear execution and dependency classes. New or materially changed tests should
use the narrowest applicable pytest marker.

| Class | Marker | External dependency | Typical scope |
|---|---|---|---|
| Unit | `unit` | None | Pure calculation, parsing, policy |
| Application | `application` | None; injected fakes allowed | Use case, lifecycle, idempotency |
| Contract | `contract` | None unless also marked integration | API, workflow, schema behavior |
| Integration | `integration` | Explicit test service | PostgreSQL, Redis, Qdrant |
| Architecture | `architecture` | None | Import and repository invariants |
| Migration | `migration` | SQLite by default; PostgreSQL when declared | Revision continuity and backfill |
| Fault injection | `fault_injection` | Declared by scenario | Timeout, concurrency, crash/recovery |

Rules:

- A test that reads `TEST_POSTGRES_URL`, `TEST_REDIS_URL`, or another external
  endpoint must carry `integration` and skip with the exact missing variable.
- Unit/default tests never use live model credentials or a serving Qdrant
  collection.
- Fault-injection tests name the bounded deadline, retry, or terminal-state
  invariant they prove.
- Reusable fixtures stay close to one domain; avoid a universal mutable fixture.
- Existing direct paths remain valid. Move a test only alongside a related code
  change and update every Makefile/CI selector atomically.

Commands:

- `make backend-fast-check`: compile and run tests that need no external service.
- `make backend-check`: compile and run the complete backend suite; unconfigured
  integration tests report explicit skips.
- `make harness-static`: architecture, documentation, baseline, and evaluation
  contracts.
