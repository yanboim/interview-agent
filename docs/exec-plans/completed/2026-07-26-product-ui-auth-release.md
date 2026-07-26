# Product UI and authentication-surface release

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Next action: schedule the isolated Vite/vue-tsc major-version upgrade tracked
  as TD-011.

## Objective

Release the typography, modal, streaming stability, dedicated conversation
history workspace, and separated product/admin login surfaces requested in the
product review.

## Non-goals

- Split product and administrator identities into separate database tables.
- Change database schema or migrate existing account ownership.
- Resolve the existing knowledge-publication or interview-idempotency debt.
- Upgrade the Vite or vue-tsc major versions.

## Acceptance criteria

- Today and interview questions use bounded responsive typography without
  horizontal overflow.
- Goal setup fits supported viewports without a nested always-visible scrollbar.
- Conversation history has a searchable `/history` workspace and is not
  embedded in the sidebar.
- Product users do not see backend navigation or API-key configuration.
- Product and admin sessions use separate browser storage and role-specific
  login endpoints; credentials from one surface are rejected by the other.
- `make harness-check` passes.
- A pre-release database backup is recorded before production containers are
  replaced.
- Production liveness, readiness, anonymous authentication, assets, desktop,
  and mobile smoke checks pass.

## Contracts and architecture rules

- Updates `responsive-accessible-shell` and adds executable user/admin surface
  and history-workspace contracts.
- Role selection belongs to `AuthService`; FastAPI routes only map application
  errors to HTTP status codes.
- No database migration is required.
- Existing P0 knowledge and interview debt remains unchanged.

## Implementation progress

- [x] Bound Today and interview typography and clamp dense card copy.
- [x] Remove nested modal overflow and collapse optional goal fields.
- [x] Add the dedicated history route and workspace.
- [x] Remove history management, backend entry, and API-key settings from the
  product shell.
- [x] Separate product/admin browser stores and login endpoints.
- [x] Move role-specific login policy from `app/main.py` into `AuthService`.
- [x] Run focused and canonical verification.
- [x] Create the pre-release production backup.
- [x] Build, deploy, and verify production.

## Decisions and findings

- Product and administrator identities remain in one authoritative identity
  table with explicit roles. Their creation path, browser session, login
  endpoint, and UI are separated. A physical table split would duplicate
  password/session security logic without improving the current authorization
  boundary.
- Valid credentials for the wrong surface are rejected before a token pair is
  issued.
- Vite/vue-tsc major-version warnings remain developer-only tracked follow-up
  and do not enter the production runtime image.

## Rollback

Re-deploy the previously running application image and preserve the PostgreSQL,
Qdrant, Redis, and knowledge volumes. This release has no schema change. The
pre-release PostgreSQL dump is an additional recovery point and must not be
committed.

The preserved image tags are:

- `interview-agent-app:rollback-20260726T0238Z`
- `interview-agent-worker:rollback-20260726T0238Z`

## Verification and release evidence

- `make harness-check` passed on 2026-07-26:
  - Harness architecture and contract checks: 6 passed.
  - Backend suite: 88 passed, 1 external-service test skipped.
  - Frontend unit suite: 8 passed.
  - Frontend type-check, production build, and bundle budgets: passed.
  - Playwright desktop/mobile acceptance suite: 8 passed.
- PostgreSQL backup:
  `backups/20260726T023800Z-pre-ui-auth.dump`, 66,418 bytes,
  SHA-256 `09ed08fcc354a079108cf7900f300b779d30c68706edca07e8f576e4046f213e`.
  The archive passed `pg_restore --list` using the production PostgreSQL
  container.
- Production images:
  - app `sha256:4f502c27fdb0ccc38309ef61ad38836736f68da8cbab6be0fb10a1d5fb1700af`
  - worker `sha256:05126bf60d8b47e5cba07b112011ba624287975e152fcf92380643d39180f495`
- Alembic remained at `20260725_0007 (head)`.
- `/health` and `/ready` returned 200; the app container was healthy and the
  worker was running.
- Data counts were unchanged at 3 users, 6 conversations, 12 messages, and 5
  interviews.
- Production desktop/mobile smoke verified meaningful content, no error
  overlay, no horizontal overflow, favicon status 200, visible login controls,
  and no unexpected console, page, or response errors.
- Invalid product/admin login probes and anonymous `/api/auth/me` returned 401.
