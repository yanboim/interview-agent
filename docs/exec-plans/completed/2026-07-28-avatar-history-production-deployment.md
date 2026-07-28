# Avatar, reminder, and interview-history production deployment

- Owner: repository maintainers
- Status: completed 2026-07-28
- Next action: monitor normal production telemetry; use the retained rollback
  images and recovery points if a delayed regression is discovered.

## Objective

Deploy the verified profile-avatar, reminder-control, and interview-history
navigation fixes to the existing single-host production Compose stack.

## Non-goals

- Replace persistent volumes or re-ingest knowledge.
- Rotate credentials or change public routing.
- Modify unrelated infrastructure services.

## Acceptance criteria

- Exact source passes `make harness-check`.
- Current application images, database revision, record counts, and Qdrant
  serving state are recorded.
- PostgreSQL and Qdrant recovery points and rollback image tags are created.
- Migration `20260728_0011` is applied by one controlled executor.
- Only app and worker are rebuilt/recreated unless dependency health requires
  otherwise.
- Health, readiness, authentication, data counts, worker state, and
  desktop/mobile browser smoke pass after deployment.

## Risks and rollback

- The migration is additive and stores an optional avatar data URL.
- Stop promotion on migration failure, readiness failure, data-count
  regression, or browser smoke failure.
- Roll back app/worker to the retained image tags without deleting volumes.
  Database restoration requires the approved backup procedure.

## Progress

- [x] Repository-wide Harness passed for the source candidate.
- [x] Production state and recovery points captured.
- [x] Rollback images retained.
- [x] Images built and application services reconciled.
- [x] Migration and post-deployment verification complete.

## Verification evidence

- Pre-deployment `make harness-check`: 176 backend tests passed, 2 skipped;
  13 frontend tests and 12 Playwright tests passed; type, build, and bundle
  gates passed.
- Pre-deployment state: app image
  `sha256:cf814a6e3b0ae65bad2ef8ec2250f22b058124451c57adf956864c4cd4152ef1`;
  worker image
  `sha256:b415a3533aacc8d7e1ac18de0bf72c2f0548b3bae3e5682fb6058e7be4d6ad6b`;
  database revision `20260728_0011`; users 4, conversations 8, messages 20,
  interviews 6; Qdrant collection green with 2,432 points.
- Recovery point: `backups/20260728T153029Z/postgres.dump` (118,963 bytes,
  82 restore-list entries) and Qdrant snapshot
  `interview_knowledge-1714474114461778-2026-07-28-15-30-50.snapshot`
  (33,179,136 bytes, checksum
  `26fa162c0fa3b2414da9a087a8cf676f5b56784651849529dec3b2b1c3121ea1`).
- Rollback tags:
  `interview-agent-app:rollback-20260728T1530Z` and
  `interview-agent-worker:rollback-20260728T1530Z`.
- Deployed images: app
  `sha256:1a679de10a03d058f142727029f120a352d7a6a1c8f377c9953bb34d2082577e`;
  worker
  `sha256:d6fcf56a538a3f3b2b9b3781b47947104ca66d02756d8b9eab454d7369ec40f0`.
- Post-deployment: `/health`, `/ready`, and gateway health passed; anonymous
  `/api/auth/me` returned 401; database remained at `20260728_0011`; record
  counts were unchanged; Qdrant remained green with 2,432 points; worker
  heartbeat was present; app and worker restart counts were zero.
- Production browser smoke passed on desktop and mobile with content and login
  controls visible, no error overlay, no horizontal overflow, no console/page
  errors, and no unexpected failed responses.

## Rollback reference

Retag the retained rollback images as the Compose app and worker images, then
recreate only those two services with `--no-build --no-deps`. Do not remove
volumes. The database was already at revision `20260728_0011` before this
release, so an application rollback does not require a schema downgrade.
