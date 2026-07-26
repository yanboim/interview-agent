# Frontend toolchain upgrade and audit

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-011
- Product contract: `frontend-toolchain-audit`

## Objective

Close the isolated Vite/vue-tsc developer-toolchain upgrade by proving the
required major versions are resolved in the lockfile, eliminating all npm audit
findings, and enforcing the upgraded baseline in local and CI gates.

## Non-goals

- Upgrade unrelated application runtime majors such as Pinia, marked, or
  vue-router.
- Change frontend product behavior or visual design.
- Require network access during every local Harness run.

## Acceptance criteria

- Vite 8, `@vitejs/plugin-vue` 6, vue-tsc 3, and Vitest 4 are both declared and
  resolved in the lockfile.
- Unrelated frontend packages are held stable unless an audit-safe update is
  required for this toolchain change.
- An offline toolchain check rejects regressions below the reviewed majors.
- Full npm audit at moderate-or-higher severity reports zero vulnerabilities,
  including developer dependencies.
- CI runs the offline check and the stricter audit.
- Unit, type, production build, bundle, Playwright, and full Harness gates pass
  without the previous six warnings.

## Progress

- [x] Direct and locked frontend toolchain versions inventoried.
- [x] Registry audit and outdated report captured.
- [x] Lockfile updated for the reviewed toolchain baseline.
- [x] Offline toolchain and CI audit gates implemented.
- [x] Full frontend and Harness verification complete.

## Decisions

- Current state already contains the required Vite/vue-tsc major upgrades, so
  the task preserves those versions and makes the baseline executable rather
  than forcing a meaningless reinstall.
- `npm audit` remains a CI network gate. The local Harness uses a deterministic
  lockfile/version check so normal verification remains offline-capable.
- Unrelated runtime major upgrades remain outside this technical-debt item.
- `@vue/test-utils` 2.4.11 was evaluated but introduced six high-severity
  findings through `js-beautify`; the audit-clean 2.2.7 release is therefore
  pinned exactly.

## Verification

- `npm ci --prefix frontend`: clean lockfile install completed and reported 0
  vulnerabilities.
- `npm run audit:dependencies --prefix frontend`: 0 vulnerabilities.
- `make frontend-check`: toolchain baseline, type-check, 10 unit tests,
  production build, and bundle budgets passed.
- `make harness-check`: 14 static checks, 154 backend tests with 2
  external-service skips, 10 frontend unit tests, and 10 Playwright tests
  passed.

## Rollback

Restore the previous package manifest and lockfile together. The change affects
build/test tooling only and has no persisted data migration.
