# Latest main production deployment

- Status: completed
- Date: 2026-07-27
- Owner: repository maintainers

## Objective

Update the production checkout to the latest reviewed `origin/main` and ensure
the exact resulting application state is deployed without losing the
production-smoke fix that is newer than the remote merge.

## Non-goals

- Merge unreviewed Dependabot branches.
- Discard or overwrite local production-smoke changes.
- Delete persistent volumes or re-ingest knowledge.
- Rotate operator credentials.

## Acceptance criteria

- Remote refs are refreshed and the checkout reaches the latest reviewed main
  commit.
- Local uncommitted changes are preserved and inventoried.
- Full Harness passes against the resulting tree.
- A fresh PostgreSQL/Qdrant recovery point and image rollback tags exist.
- Production app/worker images correspond to the resulting runtime sources.
- Migration, health, readiness, authentication, data counts, Qdrant, and
  desktop/mobile browser smoke pass.

## Progress

- [x] Remote refs fetched.
- [x] Current branch fast-forwarded from `d699956` to merged main `f3e4a02`.
- [x] Verified that the two commits have identical source trees.
- [x] Preserved the local anonymous-observability fix, regression test, and
  prior deployment record.
- [x] Harness and recovery point complete.
- [x] Runtime image/deployment state reconciled.
- [x] Production verification complete.

## Verification and recovery evidence

- The exact deployment tree passed `make harness-check`: 14 static checks, 154
  backend tests with 2 optional external-service skips, 11 frontend unit tests,
  frontend type/build/bundle gates, and 10 Playwright tests.
- PostgreSQL/Qdrant recovery point:
  `backups/20260727T020008Z`. The PostgreSQL custom archive is readable and
  contains 71 TOC entries. Qdrant snapshot
  `interview_knowledge-1714474114461778-2026-07-27-02-00-09.snapshot` is a
  healthy 33,179,136-byte snapshot of the serving collection.
- Previous runtime images remain available as
  `interview-agent-app:rollback-20260727T0200Z` and
  `interview-agent-worker:rollback-20260727T0200Z`.

## Deployment evidence

- App image:
  `sha256:4f7d9f00e0513c942d90557f88e58969a0626d9db52d84b3b40e27e5281b0016`.
- Worker image:
  `sha256:3ce2b10a789fd3dbb984bef745762c749c4778db6b563634e5d7b80afba5f6a5`.
- Only app and worker were recreated; PostgreSQL, Redis, Qdrant, and their
  persistent volumes were not replaced.
- App is healthy and worker is running. Both containers have zero restarts.
- `/health` returned `{"status":"ok"}`, `/ready` returned
  `{"status":"ready"}`, and anonymous `/api/auth/me` returned 401.
- Alembic reports `20260726_0010 (head)`.
- Post-deployment record counts are 3 users, 8 conversations, 16 messages, and
  5 interviews. The conversation/message increase from the pre-deployment
  counts occurred without any count regression.
- Qdrant is green with 2,432 indexed vectors and 2,432 points.
- Desktop 1440x900 and mobile 390x844 browser smoke loaded the `/today` UI
  without horizontal overflow, console errors, page errors, or server errors.
- The app/worker deployment-window logs contain normal migration, startup,
  readiness, metrics, and worker startup records with no errors.

## Decision

Although `d699956` and merged main `f3e4a02` have identical committed source
trees, the images were rebuilt and app/worker were reconciled because the local
anonymous-observability production fix is newer than the merge and is part of
the exact verified runtime tree.

## Operator follow-up

Resolved 2026-07-27: the repository-default Grafana administrator credential
was replaced with a generated strong credential stored only in the ignored,
mode-0600 production environment file. The persisted account was updated with
the official Grafana CLI, only Grafana was recreated, the old credential
returned 401, the replacement returned 200, and the service remained bound to
`127.0.0.1:3000`.

## Rollback

Do not remove volumes. Re-tag
`interview-agent-app:rollback-20260727T0200Z` and
`interview-agent-worker:rollback-20260727T0200Z` as the Compose app/worker
image names, run `docker compose up -d --no-build app worker`, and verify
health. If data restoration is required, use the approved restore procedure
with `backups/20260727T020008Z`; do not restore opportunistically while
requests are being served.
