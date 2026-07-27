# Durable Redis jobs

## Decision

Use Redis primitives as one small reliable queue:

```text
ready list
  -> atomic claim
processing lease ZSET
  -> acknowledge -> completed hash
  -> fail -> delayed retry ZSET -> ready list
  -> max attempts -> dead-letter list
  -> expired lease -> ready list or dead-letter list
```

Each job has one canonical hash containing its payload, state, attempt count,
maximum attempts, claim token, lease deadline, result, and error. Lua scripts
make lifecycle transitions atomic. A claim token fences acknowledgements,
failures, and heartbeats from workers that no longer own the lease.

Enqueue stores an idempotency-key mapping and the job in the same Lua
transaction. Reusing the key for the same job request returns the original job
ID; reusing it for a different request is a conflict.

The worker renews its lease while knowledge ingestion runs. Failures use
exponential delays. A reaper runs before every claim to recover expired leases
and promote due retries. Repeated worker crashes eventually exhaust the attempt
limit and dead-letter the job.

## Operational consequences

- Worker concurrency can scale horizontally without relying on process locks.
- The job hash is the operator-facing source of truth.
- DLQ replay is intentionally manual until an audited operator flow exists.
- Deployment from the previous JSON-valued ready list requires draining or
  clearing that old development queue.
