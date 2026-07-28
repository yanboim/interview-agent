# TD-012 Worker process heartbeat

- Status: completed
- Date: 2026-07-28
- Owner: repository maintainers

## Objective

Give the administrator resource center a bounded, live Worker availability
signal by publishing a process heartbeat to Redis independently of job
execution.

## Non-goals

- Treat a job lease heartbeat as proof that an idle Worker is alive.
- Expose Worker instance identifiers, Redis keys, URLs, or raw probe errors.
- Add a database table, Docker socket access, service restart action, or a new
  network service.
- Make Worker availability part of the synchronous request readiness boundary.

## Acceptance criteria

- Worker publishes a versioned heartbeat immediately at startup and refreshes
  it on a daemon thread while idle or processing a job.
- The heartbeat has a bounded Redis TTL and includes a fresh timestamp and a
  per-process instance identity.
- Missing, malformed, future-dated, or stale heartbeats fail the live probe.
- A crashed Worker becomes unavailable after the freshness window; a restarted
  Worker replaces the prior instance heartbeat and becomes healthy.
- The resource center reports Worker as healthy or unavailable without
  returning the heartbeat payload or raw errors.
- Focused tests, generated documentation, full Harness, and production smoke
  verification pass.

## Implementation plan

1. Add Redis heartbeat publish/read/freshness operations.
2. Run a process-level heartbeat publisher for the Worker lifecycle.
3. Wire the resource center Worker probe through the application Redis runtime.
4. Add crash/restart, redaction, and lifecycle tests and update contracts.
5. Run Harness, deploy App and Worker, and verify heartbeat expiry/refresh
   without disrupting data services.

## Progress

- [x] Existing Worker, Redis runtime, resource center, and deployment boundary
  inspected.
- [x] Redis heartbeat contract and Worker publisher complete.
- [x] Resource-center live probe complete.
- [x] Tests, documentation, Harness, and production deployment complete.

## Decisions

- Redis is the heartbeat source because it is already required by the Worker
  and shared with the App.
- The resource center considers at least one fresh Worker heartbeat sufficient;
  the current deployment has one Worker replica.
- Worker is operationally important but not part of synchronous API readiness,
  so its failure does not make the whole resource-center snapshot degraded.

## Verification evidence

- Focused Worker, Redis runtime, resource-center, and architecture tests:
  34 passed.
- `make harness-check`: passed in the normal host network namespace.
  - Static/architecture contracts: 16 passed.
  - Backend: 176 passed, 2 skipped.
  - Frontend unit tests: 13 passed across 5 files.
  - Frontend type-check, production build, and bundle checks: passed.
  - Playwright E2E: 12 passed.
- Production heartbeat was fresh with a configured TTL of 20 seconds and
  18 seconds remaining at the sampled point.
- Production resource snapshot reports Worker `healthy`, with 8 healthy,
  1 configured, 0 unavailable, and 0 unknown resources.
- The administrator payload contains no Worker instance identity, heartbeat
  timestamp, or Redis heartbeat key.
- Production App is healthy and Worker is running; both have restart count 0.
- Production images:
  - App:
    `sha256:cf814a6e3b0ae65bad2ef8ec2250f22b058124451c57adf956864c4cd4152ef1`.
  - Worker:
    `sha256:b415a3533aacc8d7e1ac18de0bf72c2f0548b3bae3e5682fb6058e7be4d6ad6b`.
- Rollback images:
  - `interview-agent-app:rollback-td012-20260728`.
  - `interview-agent-worker:rollback-td012-20260728`.

## Unexpected findings

- A parallel avatar-settings change modified its E2E test during the first
  Harness attempts. Those user changes were preserved. The final stable
  worktree passed all 12 E2E tests.
- Playwright WebServer discovery cannot connect through the restricted sandbox
  network namespace. The approved full Harness passed in the normal host
  network namespace.

## Rollback

Restore the prior App and Worker images together. The heartbeat key expires
automatically and requires no data migration or cleanup.
