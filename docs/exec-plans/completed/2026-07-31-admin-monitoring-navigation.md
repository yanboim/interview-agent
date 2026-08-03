# Administrator monitoring navigation

- Status: completed
- Date: 2026-07-31
- Completed: 2026-08-01
- Owner: repository maintainers

## Objective

Add safe Prometheus and Grafana entry links to the authenticated administrator
navigation while preserving the existing private infrastructure boundary.

## Non-goals

- Expose Prometheus, Grafana, databases, Redis, or Qdrant publicly.
- Embed credentials in URLs or frontend bundles.
- Proxy infrastructure consoles through the application.
- Change monitoring authentication or network policy.

## Acceptance criteria

- Operators can configure credential-free HTTP(S) URLs for Prometheus and
  Grafana independently.
- The administrator runtime response includes only links that pass the existing
  scheme, host, and credential checks.
- Configured links appear in a distinct administrator navigation group, open in
  a new browsing context, and use `noopener noreferrer`.
- Missing or unsafe URLs do not create navigation links.
- Focused backend/frontend/browser checks and the repository Harness pass.
- Generated references and the Simplified Chinese mirror are synchronized.

## Progress

- [x] Existing resource-center link model and administrator shell inspected.
- [x] Backend configuration and safe link projection implemented.
- [x] Administrator navigation and tests implemented.
- [x] Documentation generated and canonical verification completed.

## Verification evidence

- `tests/test_system_resources.py`: 6 passed during focused development.
- Frontend type-check, production build, and 22 unit tests passed.
- Responsive desktop and mobile browser behavior is covered by the repository
  browser suite.
- `make docs-generate` synchronized 120 generated and mirrored documents.
- `make harness-check` passed on 2026-08-01: 279 backend tests passed with 2
  optional skips, 22 frontend unit tests passed, and 28 browser tests passed.

## Rollback

Remove the optional URL settings and navigation projection. No database,
migration, persistent volume, or monitoring-service change is required.
