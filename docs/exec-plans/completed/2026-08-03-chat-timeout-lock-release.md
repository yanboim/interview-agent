# Chat timeout lock release

- Status: completed
- Date: 2026-08-03
- Owner: repository maintainers

## Objective

Ensure a Workflow V2 chat request that times out or is cancelled always reaches
a durable terminal turn state and releases its conversation ownership. Bound
expert-task cancellation cleanup so an uncooperative provider task cannot keep
the HTTP stream and idempotency lock open indefinitely.

## Non-goals

- Do not take over a still-running turn by a background time-based lease.
- Do not replay a partially emitted answer or weaken idempotency fencing.
- Do not change authentication, provider credentials, or production model
  routing.

## Acceptance criteria

- Explicit specialist siblings are cancelled on failure and drained only for a
  bounded grace period.
- A parent timeout/cancellation is not blocked while draining an uncooperative
  sibling task.
- Existing sibling-cancellation and deterministic ordering behavior remains
  covered by tests, with a regression test for an uncooperative task.
- Focused tests, `make pr-check`, and the required release Harness pass before
  deployment or handoff.

## Implementation steps

- [x] Capture production evidence and recover the confirmed stale turn using
  the existing owner-confirmed recovery command.
- [x] Add bounded cancellation/drain behavior to the Workflow V2 executor.
- [x] Add regression coverage and update reliability/operator documentation.
- [x] Run focused checks and repository gates; record evidence and rollback.

## Completion evidence

- The executor now detects parent cancellation, fences the durable turn in the
  application use case, and detaches only uncooperative sibling tasks with
  observed exceptions. Normal sibling failures still receive a one-second
  bounded drain.
- Focused chat execution/use-case/lifecycle/model-gateway tests: 38 passed.
  `make pr-check`: backend 343 passed/2 deselected, architecture and harness
  contracts 30 passed, frontend type/unit/build/bundle checks passed.
  `make harness-check`: backend 343 passed/2 skipped and frontend checks passed;
  the parallel browser stage had one known timing failure in
  `admin-audits.spec.ts` (29/30). The exact file rerun serially passed 2/2,
  matching a test timing flake rather than a chat regression.
- Production app and worker run the same image content ID
  `sha256:539b9975ec7e855e3667da078b842ed55764258ba7520ec5835ed4ccc9bd0a71`.
  Image-internal source hashes matched the workspace; health and authenticated
  readiness passed. A real streaming probe emitted
  `token,sources,citations,done`.
- A separate live probe received a provider 503; after the failure the database
  reported zero `generating` turns, demonstrating the repaired terminal-state
  path. All three probe identities were then removed by exact UUID+username
  transactions; users, tokens, conversations, turns, and traces verified zero.
- The local Trivy executable was unavailable and the security policy rejected a
  third-party scanner reading private image tars. The candidate has unchanged
  base/dependency layers from the previously scanned r9 image; this limitation
  is recorded in the release ledger as `trivy_dependency_baseline` rather than
  claiming a new scan.
- Production ledger release:
  `production-chat-timeout-lock-release-20260803-539b9975ec7e-r11` (`succeeded`).

## Rollback

No migration is required. Revert the executor change and redeploy the recorded
rollback labels `interview-agent-app:rollback-chat-timeout-lock-release-20260803`
and `interview-agent-worker:rollback-chat-timeout-lock-release-20260803` together
if a release gate fails.
