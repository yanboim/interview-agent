# Interview typography production deployment

- Owner: repository maintainers
- Status: completed 2026-07-31
- Next action: monitor normal production telemetry and confirm long interview
  questions remain comfortable to read at common desktop zoom levels.

## Objective

Deploy the verified long-interview-question typography adjustment to the
existing single-host production Compose stack.

## Non-goals

- Change interview content, persistence, knowledge data, or public routing.
- Rebuild the Worker or unrelated infrastructure services.

## Acceptance criteria

- The exact source candidate passes `make harness-check`.
- Current application image, database revision, core counts, and dependency
  health are captured before deployment.
- A PostgreSQL recovery point and application rollback image are retained.
- Only the application image and container are rebuilt and recreated.
- Health, readiness, authentication, data, Worker heartbeat, and production
  desktop/mobile browser smoke pass after deployment.
- The successful release is recorded in the administrator ledger.

## Risks and rollback

- This is a CSS and browser-regression-only change with no schema migration.
- Stop on build failure, readiness failure, data regression, or browser smoke
  failure.
- Roll back the application to the retained image without deleting volumes.

## Progress

- [x] Exact source passed the full repository Harness.
- [x] Production baseline and recovery point captured.
- [x] Application rollback image retained.
- [x] Application service updated.
- [x] Post-deployment verification and release recording complete.

## Unexpected finding and containment

- The first full-workspace candidate contained migration `20260730_0017`,
  which belongs to the still-active Agent hardening program. Application startup
  applied the additive migration before the scope mismatch was identified.
- The new `agent_action_confirmations` table remained empty. Core record counts
  were unchanged and no unfinished Agent capability was enabled in the final
  production application.
- A direct application rollback could not start because its migration graph did
  not recognize the already-applied revision. Two derived candidates were
  rejected by startup/readiness checks due to a copied-file permission issue
  and an inherited temporary command. The verified workspace candidate restored
  service between attempts.
- The final immutable image is based on the pre-deployment application image,
  adds only the verified typography asset and the `0017` migration definition
  required to recognize the existing additive schema, and preserves the
  original application command and non-root user.

## Verification evidence

- Pre-deployment `make harness-check`: generated references and Chinese mirror
  current; 17 static/architecture tests passed; 228 backend tests passed, 2
  skipped; 18 frontend unit tests and 24 desktop/mobile Playwright tests passed;
  type, build, bundle, and toolchain gates passed.
- Baseline: application image
  `sha256:3e3b8858d040aeea6753c5be0c391cee45722a6bfc014fd5c638f9fc7293db6d`;
  database revision `20260729_0016`; users 4, conversations 9, messages 26,
  interviews 8; Qdrant green with 2,432 points.
- PostgreSQL recovery point:
  `backups/20260731T093849Z/postgres.dump` (285,126 bytes, readable restore
  list).
- Rollback image: `interview-agent-app:rollback-20260731T0938Z`.
- Final production image:
  `sha256:476d3b6d0fd1eeee585c4239ff04fe4f10eb5cf7505cc2d10a18c23f2534d3e7`,
  labeled `interview.release.scope=interview-typography-only`.
- Production CSS serves `clamp(18px, 1.15vw, 20px)`, weight `600`, line-height
  `1.65`, and the mobile `18px` rule.
- `/health`, `/ready`, and gateway health passed; anonymous `/api/auth/me`
  returned 401; users/conversations/messages/interviews remained `4/9/26/8`;
  `agent_action_confirmations` remained empty; Worker heartbeat was fresh;
  Qdrant remained green with 2,432 points; app and Worker restart counts were
  zero after final promotion.
- Production desktop/mobile browser smoke passed without error overlays,
  horizontal overflow, console/page errors, or unexpected failed responses.
- Administrator release ledger records
  `production-20260731T093849Z | 2026.07.31.0938 | production | succeeded |
  20260730_0017`.

## Rollback reference

The application rollback image cannot run against revision `0017` unless the
`0017` migration definition is also present. Prefer retagging the verified
final typography image for routine restart. A database downgrade or restore is
destructive and still requires separate operator confirmation.
