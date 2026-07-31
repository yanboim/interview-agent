# Resume and interview-review production deployment

- Owner: repository maintainers
- Status: completed 2026-07-29
- Scope: existing single-host production Compose stack

## Objective

Deploy the verified resume assessment, resume-grounded mock interview, and
text-based real interview review features. Keep audio transcription disabled.

## Non-goals

- Configure or call an audio transcription provider.
- Replace persistent volumes, re-ingest knowledge, or change public routing.
- Modify production secrets unrelated to the three feature flags.

## Acceptance criteria

- The exact source candidate passes `make harness-check`.
- Current service health, database revision, core counts, and recovery points
  are captured before deployment.
- Rollback images for the current App and Worker are retained.
- `RESUME_FEATURE_ENABLED=true`, `REVIEW_FEATURE_ENABLED=true`, and
  `TRANSCRIPTION_ENABLED=false` are active in the deployed containers.
- Database migrations advance through revision `20260729_0016`.
- App, Worker, gateway, PostgreSQL, Redis, and Qdrant remain healthy.
- Health, readiness, authentication, text review, and resume entry-point smoke
  checks pass without exposing or changing user content.
- The deployment is recorded in the production release ledger.

## Risks and rollback

- Revisions `0014` through `0016` add resume, interview-source, and review
  tables/columns. Take a PostgreSQL backup before migrating.
- User uploads require the persistent user-file volume to remain mounted.
- On application failure, stop promotion and restore the retained App/Worker
  images. Database downgrade or restore requires explicit operator approval;
  do not delete volumes.
- Audio upload/transcription must remain unavailable until provider, region,
  retention, and cost approval is complete.

## Progress

- [x] Exact source passed the full repository Harness.
- [x] Production baseline and recovery points captured.
- [x] Feature configuration updated with transcription disabled.
- [x] Application services built, migrated, and deployed.
- [x] Post-deployment smoke checks passed.
- [x] Production release ledger recorded.

## Verification evidence

- Pre-deployment Harness: 217 backend tests passed, 2 skipped; 18 frontend unit
  tests and 22 desktop/mobile Playwright tests passed; architecture, type,
  build, bundle, and static documentation gates passed.
- Baseline: database revision `20260728_0013`; users 4, conversations 9,
  messages 24, interviews 8; Qdrant green with 2,432 points; the user-file
  volume contained no files.
- Recovery point: `backups/20260729T022931Z/postgres.dump` (172,532 bytes,
  97 readable restore-list entries) and Qdrant snapshot
  `interview_knowledge-1714474114461778-2026-07-29-02-29-56.snapshot`.
- Rollback images:
  `interview-agent-app:rollback-20260729T0229Z` and
  `interview-agent-worker:rollback-20260729T0229Z`.
- The initial candidate exposed a Python 3.12-only startup failure: the class
  method named `list` shadowed the built-in used by a later evaluated type
  annotation. Local verification used Python 3.14, where annotation evaluation
  is deferred. The candidate was retained under `failed-candidate` tags; the
  application was restored while the source added
  `from __future__ import annotations`.
- The corrected production Python 3.12 image successfully imported both the
  interview-review service and application composition root before restart.
- Database revision is `20260729_0016`; existing user, conversation, message,
  and interview counts are unchanged. New resume and review tables are empty.
- Active configuration reports resume and review enabled and transcription
  disabled. Health, readiness, anonymous authorization boundaries, Worker
  heartbeat, Qdrant health, and deployment-window logs passed.
- Production browser smoke passed for `/today`, `/resumes`, and `/reviews`:
  login protection was visible, there was no horizontal overflow, and no
  console or page errors were observed.
- Final images: App
  `sha256:10434aafdab7249d5bb72be0ad2ff61e713324fa9f7fe2cf23f0f175e456e0eb`
  and Worker
  `sha256:98ff4e46338c61b84a4d6f3eed750520981d13ff611323fd62d4db9ebf6bdeaf`;
  both have zero restarts.
- Release ledger:
  `production-20260729T022931Z | 2026.07.29.0240 | production | succeeded |
  20260729_0016`.
- Post-fix repository Harness passed again: 217 backend tests passed with 2
  environment-gated skips, 18 frontend unit tests passed, and all 22
  desktop/mobile Playwright checks passed.
