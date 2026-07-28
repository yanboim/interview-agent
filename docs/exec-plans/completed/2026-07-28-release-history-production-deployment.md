# Release history production deployment

- Owner: repository maintainers
- Status: completed 2026-07-28
- Next action: monitor normal production telemetry and confirm administrators
  can see release `2026.07.28.1703`.

## Objective

Deploy the verified administrator release-history and current administrator
observability changes to the existing single-host production Compose stack,
then use the new operator command to record this deployment.

## Non-goals

- Replace persistent volumes, re-ingest knowledge, or change public routing.
- Rotate credentials or expose operational metadata to product users.
- Recreate infrastructure services that are already healthy.

## Acceptance criteria

- Exact source passes `make harness-check`.
- Production images, migration revision, data counts, and Qdrant state are
  captured before deployment.
- PostgreSQL, Qdrant, and rollback-image recovery points are verified.
- Migrations `20260728_0012` and `20260728_0013` apply linearly.
- Only app and worker are rebuilt/recreated.
- Health, readiness, authentication, data counts, worker heartbeat, sanitized
  administrator release API, and desktop/mobile production browser smoke pass.
- The successful deployment appears in the administrator release ledger.

## Risks and rollback

- Both migrations are additive. Prefer retaining the new schema when rolling
  back application images.
- Stop on migration failure, readiness failure, data regression, permission
  failure, or browser smoke failure.
- Roll back app/worker using retained image tags without deleting volumes.
  Database restore remains a separately approved destructive operation.

## Progress

- [x] `make harness-check` passed: 180 backend tests, 2 skipped; 13 frontend
  unit tests; 14 desktop/mobile Playwright tests; static, type, build, bundle,
  and toolchain gates passed.
- [x] Production baseline captured.
- [x] Recovery points and rollback images retained.
- [x] Application services updated.
- [x] Post-deployment checks and release recording complete.

## Baseline

- Captured at `20260728T170319Z`.
- App image:
  `sha256:1a679de10a03d058f142727029f120a352d7a6a1c8f377c9953bb34d2082577e`.
- Worker image:
  `sha256:d6fcf56a538a3f3b2b9b3781b47947104ca66d02756d8b9eab454d7369ec40f0`.
- Database revision: `20260728_0011`.
- Users 4, conversations 8, messages 20, interviews 6.
- Qdrant `interview_knowledge` green with 2,432 indexed vectors and points;
  no aliases.
- App, gateway, PostgreSQL, Redis, and Qdrant healthy; `/health` and `/ready`
  passed.

## Verification evidence

- Recovery directory: `backups/20260728T170319Z`.
- PostgreSQL dump: 119,073 bytes and 82 readable restore-list entries.
- Qdrant snapshot:
  `interview_knowledge-1714474114461778-2026-07-28-17-04-00.snapshot`,
  33,179,136 bytes, checksum
  `9544f74b0cee474c8fe1733bab79375b677dabb01e958246f76bf686a6a8b17c`.
- Rollback images:
  `interview-agent-app:rollback-20260728T1703Z` and
  `interview-agent-worker:rollback-20260728T1703Z`.
- Deployed app image:
  `sha256:346d2c2684733c802bb55fa1a529a500ebb81a35491c7c4e2af474a7b90f160d`.
- Deployed worker image:
  `sha256:f7a35ccf2ec41c10fae65c03efb1753915277e9b2808946c9b1f7619924af574`.
- Alembic applied `20260728_0011 -> 20260728_0012 -> 20260728_0013`;
  current and head both report `20260728_0013`.
- Core data remained users 4, conversations 8, messages 20, interviews 6.
- Qdrant remained green with 2,432 indexed vectors and points.
- `/health`, `/ready`, and gateway health passed; anonymous `/api/auth/me`
  returned 401; worker heartbeat was present; app and worker restart counts
  were zero; deployment logs contained no runtime errors.
- Production desktop/mobile browser smoke passed with no error overlay,
  horizontal overflow, console/page errors, or unexpected failed responses.
- The new operator command recorded
  `production-20260728T170319Z | 2026.07.28.1703 | production | succeeded |
  20260728_0013`, and the record was read back from PostgreSQL.

## Rollback reference

Retag the retained rollback images as the Compose app and worker images, then
recreate only those two services with `--no-build --no-deps`. Keep migrations
`0012` and `0013` because they are additive and the previous application does
not depend on their absence. Do not remove volumes. Use the database recovery
point only after separate destructive-restore approval.
