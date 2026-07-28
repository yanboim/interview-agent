# Administrator release history

- Owner: repository maintainers
- Status: completed 2026-07-28
- Next action: deploy migration `20260728_0013`, then make the recording command
  the final step of the production deployment executor.

## Objective

Provide administrators with an automated, read-only history of verified
deployments. A release becomes authoritative only when the deployment process
records its outcome; Git commits alone are not treated as production releases.

## Non-goals

- Build a public product changelog or expose releases to product users.
- Add a manual rich-text publishing workflow, comments, likes, or notifications.
- Replace the existing release, backup, deployment, or rollback runbooks.

## Acceptance criteria

- Alembic creates an idempotent deployment-release ledger with explicit
  environment and lifecycle status.
- A retry-safe operator command records deployment outcomes and structured
  verification evidence.
- Only authenticated administrators can list recent releases.
- The administrator console shows reverse-chronological timeline cards and an
  accessible detail drawer without horizontal overflow.
- Empty, loading, success, failed, and rolled-back states are understandable.
- Backend, migration, frontend, and browser acceptance tests cover the behavior.
- The product feature contract and deployment documentation describe the
  automated record boundary.

## Architecture and contract impact

- The database mutation remains in `ConversationStore`; the API router is a
  read-only administrator adapter.
- Release writes are performed by an operator-side command using a stable
  release ID so retries update one ledger record rather than creating duplicates.
- No user-owned data is read or written, and the API continues to use the
  server-resolved administrator role.
- Migration `20260728_0013` is additive and follows the existing administrator
  observability migration.

## Implementation steps

1. Add the release table, migration, store methods, and operator recording CLI.
2. Add the administrator-only list endpoint and typed frontend client/store.
3. Build the timeline, filters, and accessible detail drawer.
4. Add focused tests and update product/release documentation.
5. Run `make harness-check`, record evidence, and archive this plan.

## Risks and rollback

- Release details can contain operational metadata. The UI and API must not
  accept or expose credentials, connection strings, or raw logs.
- The table is additive and independent of product-user data. Application
  rollback can leave it in place; schema rollback drops only release records.
- A failed recording call must not change the deployment result itself.

## Progress

- [x] Existing architecture, contracts, administrator surface, and release
  process inspected.
- [x] Persistence and operator automation implemented.
- [x] Administrator API and UI implemented.
- [x] Focused and repository-wide verification complete.

## Verification evidence

- Focused backend and migration tests: 8 passed.
- Focused administrator release browser acceptance: desktop and mobile passed.
- `make harness-check`: 16 static/architecture checks passed; 180 backend
  tests passed with 2 skipped; 13 frontend unit tests passed; type, production
  build, bundle budgets, and toolchain checks passed; 14 Playwright tests
  passed across desktop and mobile.
- Browser acceptance verified no horizontal overflow, no serious accessibility
  violations, Escape-to-close, focus restoration, and release detail content.

## Decisions and findings

- The current GitHub release workflow verifies and packages artifacts but does
  not deploy production. Therefore the repository supplies a deployment-agnostic
  recording command and makes it the final step of the deployment runbook.
- The initial UI uses a timeline and detail drawer because recent release
  volume is low; no editable changelog CMS is introduced.
- An administrator observability migration already occupied `20260728_0012`
  during implementation. The release ledger was moved to `20260728_0013` to
  preserve a single linear migration head.
