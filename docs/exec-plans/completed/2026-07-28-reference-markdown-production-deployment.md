# Reference Markdown production deployment

- Owner: repository maintainers
- Status: completed 2026-07-28
- Next action: monitor normal production telemetry and confirm reference
  answers render correctly for existing and newly generated interview results.

## Objective

Deploy the verified reference-answer Markdown rendering fix to the existing
single-host production Compose stack.

## Non-goals

- Replace persistent volumes, re-ingest knowledge, or change public routing.
- Apply database migrations or modify unrelated infrastructure.

## Acceptance criteria

- The exact source candidate has passed `make harness-check`.
- Current images, database revision, core counts, and dependency health are
  captured before deployment.
- Recovery points and rollback image tags are retained.
- Only app and worker are rebuilt and recreated.
- Health, readiness, authentication, worker state, and production browser
  smoke pass after deployment.
- The successful production release is recorded in the administrator ledger.

## Risks and rollback

- The change is application-only and requires no schema migration.
- Stop on build failure, readiness failure, data regression, or browser smoke
  failure.
- Roll back app and worker to the retained image tags without deleting volumes.

## Progress

- [x] Exact source passed the full repository Harness.
- [x] Production baseline and recovery points captured.
- [x] Rollback images retained.
- [x] Application services updated.
- [x] Post-deployment verification and release recording complete.

## Verification evidence

- Pre-deployment Harness: 186 backend tests passed, 2 skipped; 14 frontend unit
  tests and 16 desktop/mobile Playwright tests passed; static, type, build,
  bundle, and toolchain gates passed.
- Baseline: database revision `20260728_0013`; users 4, conversations 8,
  messages 20, interviews 6; Qdrant green with 2,432 indexed vectors and
  points.
- PostgreSQL recovery point:
  `backups/20260728T181725Z/postgres.dump` (139,432 bytes, readable restore
  list).
- Qdrant snapshot:
  `interview_knowledge-1714474114461778-2026-07-28-18-18-07.snapshot`
  (33,179,136 bytes, checksum
  `d7e05a68c9051a8cdeb8973056ea3e02375b77160bb60de35642795572a54d19`).
- Rollback images:
  `interview-agent-app:rollback-20260728T1817Z` and
  `interview-agent-worker:rollback-20260728T1817Z`.
- Deployed app image:
  `sha256:305fda35ed673b7e2d86a99bb0aebd209e2e07f974415a5cc7e44b96332138c3`.
- Deployed worker image:
  `sha256:fd519ca29cb4abb06475673f3642c12fad0eb4c948b4701044c3b4bf3a7c1adc`.
- Post-deployment `/health`, `/ready`, and gateway health passed; anonymous
  `/api/auth/me` returned 401; database revision and core counts were unchanged;
  Worker heartbeat was fresh; Qdrant remained green with 2,432 points; app and
  Worker restart counts were zero.
- Production desktop/mobile browser smoke passed with content and login controls
  visible, no error overlay, horizontal overflow, console/page errors, or
  unexpected failed responses.
- Administrator release ledger records
  `production-20260728T181725Z | 2026.07.28.1817 | production | succeeded |
  20260728_0013`.

## Rollback reference

Retag the retained rollback images as the Compose app and worker images, then
recreate only those two services with `--no-build --no-deps`. Do not remove
volumes. This release has no schema migration, so application rollback does not
require a database downgrade.
