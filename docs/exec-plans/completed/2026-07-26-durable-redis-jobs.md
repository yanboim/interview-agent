# Durable Redis jobs

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-006
- Product contract: `durable-background-jobs`

## Objective

Replace destructive `BLPOP` job consumption with an owner-fenced lifecycle that
survives worker crashes, retries transient failures, dead-letters exhausted
jobs, and deduplicates retried enqueue commands.

## Non-goals

- Introduce a third-party workflow engine.
- Make knowledge publication itself synchronous with the HTTP request.
- Automatically replay dead-letter jobs.
- Add new background job types.

## Acceptance criteria

- Enqueue is atomic and accepts a request idempotency key.
- A job has canonical Redis metadata and queued, running, retry-scheduled,
  completed, or dead status.
- Claim assigns an owner token, attempt number, and renewable lease atomically.
- Acknowledge/fail/heartbeat reject stale owners.
- Expired leases return to ready state until max attempts, then enter DLQ.
- Failures use bounded exponential retry scheduling.
- Worker tests cover success, retry, recovery, and exhaustion semantics.
- Status remains available through the existing admin endpoint.
- `make harness-check` passes.

## Progress

- [x] Existing BLPOP loss window and job API inspected.
- [x] Atomic enqueue/claim/ack/fail/heartbeat/recovery scripts implemented.
- [x] Worker migrated to lease-based claims and exponential retry.
- [x] Live Redis lifecycle verified through `TEST_REDIS_URL`.
- [x] Documentation, contract, and full Harness complete: 11 static checks;
      130 backend tests passed with 2 optional integration tests skipped in the
      default suite; the Redis integration test passed explicitly; 10 frontend
      unit tests, type-check, production build, bundle budgets, and 10
      Playwright scenarios passed.

## Findings

- The old worker's destructive `BLPOP` was replaced rather than wrapped,
  because no acknowledgement can recover an item after `BLPOP` removes it.
- Lease recovery checks the attempt count. Repeated hard crashes therefore
  eventually dead-letter instead of cycling forever.
- The idempotency mapping and job creation occur in one Lua script, avoiding a
  dangling mapping if a process dies between two Redis calls.

## Rollback

No persistent database migration is involved. Existing queued JSON list entries
from the old worker are not compatible with the new job-ID list format; drain
or clear the old development queue before deployment. Job status hashes retain
the same key prefix and status endpoint.
