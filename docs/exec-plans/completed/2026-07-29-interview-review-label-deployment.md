# Interview review label deployment

- Owner: repository maintainers
- Status: completed 2026-07-29

## Objective

Use the four-character product name “面试复盘” consistently in the current
interface, user-facing messages, learning-topic output, and product
documentation, then deploy the application-only change.

## Non-goals

- Rename APIs, database tables, source identifiers, or stored review records.
- Enable audio transcription or change feature configuration.
- Apply database migrations or modify persistent volumes.

## Acceptance criteria

- No current user-facing occurrence of “真实面试复盘” remains.
- Backend, frontend, documentation, and full repository checks pass.
- Existing App and Worker images are retained for rollback.
- The production App and Worker use the same verified source image set.
- Health, readiness, four-character production UI text, and zero-restart
  checks pass.
- The production release ledger records the deployment.

## Progress

- [x] Product naming updated consistently.
- [x] Focused and full repository checks passed.
- [x] Rollback images retained and corrected images built.
- [x] Production services deployed and verified.
- [x] Release ledger recorded.

## Verification evidence

- `make harness-check`: 217 backend tests passed with 2 environment-gated
  skips, 18 frontend unit tests passed, and all 22 desktop/mobile browser tests
  passed.
- Rollback images:
  `interview-agent-app:rollback-20260729T0250Z` and
  `interview-agent-worker:rollback-20260729T0250Z`.
- Production Python 3.12 import validation passed before deployment.
- Production App image:
  `sha256:f9886047147b8cfb4a8db50a6d2efcc00e4d4ec47b0c9d2a44e76dce07b19d76`;
  Worker image:
  `sha256:c434aa9e3d03ca805d4362771c8468da78c088f1c55f121243ebf71dd4becabc`.
- Health and readiness passed; App and Worker have zero restarts; the Worker
  heartbeat is fresh; audio transcription remains disabled.
- The production bundle and `/reviews` browser page contain “面试复盘” and do
  not contain “真实面试复盘”. Browser console/page errors and horizontal overflow
  were absent.
- Release ledger:
  `production-20260729T025024Z | 2026.07.29.0252 | production | succeeded |
  20260729_0016`.
