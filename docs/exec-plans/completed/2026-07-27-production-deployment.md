# Production deployment

- Status: completed
- Date: 2026-07-27
- Owner: repository maintainers

## Objective

Deploy the verified TD-006 through TD-011 repository state to the existing
single-host Compose production stack while preserving PostgreSQL and Qdrant
recovery points and proving application readiness after migration.

## Non-goals

- Delete or replace persistent volumes.
- Re-ingest or switch the serving knowledge collection.
- Rotate application, model-provider, or operator credentials.
- Expose internal service ports publicly.

## Acceptance criteria

- The current PostgreSQL database and serving Qdrant collection have a
  deployment-time backup record.
- Existing app and worker image IDs are retained as rollback tags.
- `make harness-check` passes for the exact source being deployed.
- Images build from the committed immutable inputs.
- Compose updates the stack without removing named volumes.
- Alembic reaches the repository head.
- App and dependencies are healthy; liveness, readiness, authentication,
  frontend assets, worker, and persistent record counts pass smoke checks.
- Deployment evidence and the rollback command are recorded here.

## Progress

- [x] Deployment instructions, current Compose state, safety configuration,
  image IDs, database revision, and record counts inspected.
- [x] Pre-deployment Harness complete.
- [x] PostgreSQL and Qdrant backup created and validated.
- [x] Rollback image tags retained.
- [x] Production images built and stack updated.
- [x] Migration, health, smoke, and data-integrity checks complete.

## Pre-deployment state

- App image: `sha256:7c5aa74f48058bf49c75fc2a0615597bfa28a06d8d674d03ebeb5ac73e0df364`
- Worker image:
  `sha256:05126bf60d8b47e5cba07b112011ba624287975e152fcf92380643d39180f495`
- Alembic: `20260725_0007`
- Record counts: 3 users, 7 conversations, 14 messages, 5 interviews.
- App, PostgreSQL, Redis, and Qdrant reported healthy before deployment.
- Backup: `backups/20260727T004506Z`; PostgreSQL custom archive contains
  63 TOC entries, and Qdrant snapshot
  `interview_knowledge-1714474114461778-2026-07-27-00-45-07.snapshot`
  covers the healthy 2,432-point serving collection.
- Rollback tags: `interview-agent-app:rollback-20260727T0045Z` and
  `interview-agent-worker:rollback-20260727T0045Z`.
- Pre-deployment `make harness-check`: 14 static checks, 154 backend tests
  passed with 2 optional external-service skips, 10 frontend unit tests,
  frontend type/build/bundle gates, and 10 Playwright tests passed.

## Deployment evidence

- Final app image:
  `sha256:e0ee17303eea9764baa0d22f16d23aa33ff7d4bd50c78fc1a3d193ec227f62f0`.
- Final worker image:
  `sha256:99e9254640ae9ad8627123cfa2f0ef11e70e88a79780317dbe2a30ba5b5fe6a1`.
- App, PostgreSQL, Redis, and Qdrant are healthy; Worker, Prometheus, Grafana,
  and OpenTelemetry Collector are running. App and Worker restart counts are
  zero.
- `/health` returned `{"status":"ok"}` and `/ready` returned
  `{"status":"ready"}`.
- Alembic reached `20260726_0010 (head)`.
- Record counts remained 3 users, 7 conversations, 14 messages, and 5
  interviews.
- Qdrant remained green with 2,432 points after changing from the mutable old
  container reference to the reviewed `v1.15.1` digest.
- Anonymous `/api/auth/me` returned 401.
- Desktop 1440×900 and mobile 390×844 browser smoke loaded meaningful UI with
  no horizontal overflow, console errors, page errors, or failed resources.

## Deployment finding

The first production browser smoke found that anonymous client-observability
events were sent to the authenticated `/api/product-events` endpoint, causing a
401 resource error on the login screen. Observability now checks the live auth
state before emitting protected events. A focused regression test was added,
and the final `make harness-check` passed 14 static checks, 154 backend tests
with 2 optional skips, 11 frontend unit tests, frontend type/build/bundle
gates, and 10 Playwright tests before the corrected app image was deployed.

## Operator follow-up

Resolved 2026-07-27: the repository-default Grafana administrator credential
was replaced with a generated strong credential stored only in the ignored,
mode-0600 production environment file. The persisted Grafana account was
updated through the official CLI, only Grafana was recreated, the old
credential returned 401, the replacement returned 200, and the service
remained restricted to `127.0.0.1:3000`.

## Rollback

Do not remove volumes. Re-tag
`interview-agent-app:rollback-20260727T0045Z` and
`interview-agent-worker:rollback-20260727T0045Z` as the Compose app/worker
image names, run `docker compose up -d --no-build app worker`, and verify
health. If the database migration itself must be reversed, stop promotion and
use the approved PostgreSQL restore procedure with
`backups/20260727T004506Z`; do not downgrade or restore opportunistically while
requests are still being served.
