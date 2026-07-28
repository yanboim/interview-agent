# System resource center

- Status: completed
- Date: 2026-07-28
- Owner: repository maintainers

## Objective

Add an administrator-only system resource center that provides one sanitized
inventory and health view for the gateway, application, worker, data stores,
and observability services without turning the product gateway into a public
proxy for infrastructure consoles.

## Non-goals

- Expose PostgreSQL, Redis, Qdrant, Prometheus, Grafana, or OpenTelemetry.
- Return connection strings, credentials, internal probe URLs, or raw
  exception messages.
- Add restart, restore, shell, SQL, or arbitrary infrastructure actions.
- Claim Worker or OpenTelemetry health without a reliable live probe.
- Modify unrelated lifecycle-documentation work already present in the
  worktree.

## Acceptance criteria

- `/api/admin/resources` requires the server-resolved administrator role.
- The response inventories Nginx, App, Worker, database, Redis, Qdrant,
  Prometheus, Grafana, and OpenTelemetry with status, exposure, criticality,
  description, and runbook metadata.
- Live checks have bounded timeouts and generic failure details; unavailable
  services do not leak their URL or exception.
- Optional console links accept only credential-free HTTP(S) URLs and are
  absent by default.
- The Vue administrator console has a responsive resource-center section with
  refresh, status summary, exposure labels, and optional controlled links.
- Backend, frontend, architecture, product-contract, Harness, and production
  smoke verification pass.

## Implementation plan

1. Add a transport-independent resource inventory/probe service and compose it
   at application startup.
2. Add the administrator endpoint, product contract, and negative/redaction
   tests.
3. Add frontend types, API/store integration, resource page, and responsive
   styles.
4. Regenerate configuration documentation, run focused and full gates, deploy,
   and verify through Nginx.

## Progress

- [x] Existing admin runtime API, UI, security boundary, Compose services, and
  parallel changes inventoried.
- [x] Backend resource service and endpoint complete.
- [x] Frontend resource center complete.
- [x] Verification and production deployment complete.

## Verification evidence

- `make harness-check`: passed.
  - Static/architecture contracts: 16 passed.
  - Backend: 162 passed, 2 skipped.
  - Frontend unit tests: 13 passed across 5 files.
  - Frontend type-check, production build, and bundle checks: passed.
  - Playwright E2E: 10 passed.
- Generated API-route and configuration references are current.
- Production application image:
  `sha256:16260ccb694d34b8b484cf48b6331ed4f42e6fe0208095d1742a26235c48489a`.
- Previous application image retained as
  `interview-agent-app:rollback-resource-center-20260728`.
- Production application health is `healthy` with restart count `0`.
- Sanitized production snapshot is `healthy`: seven resources healthy,
  OpenTelemetry configured, Worker unknown, and no unavailable resource.
- The snapshot contains no database/Redis connection string, password, secret,
  or token; optional console links are absent by default.
- Unauthenticated `GET /api/admin/resources` returns `401`.
- Browser smoke through Nginx at `/admin` returns `200`, renders meaningful
  content, has no framework error overlay, and reports no console errors.
- The deployed admin bundle contains the system resource center.

## Rollback

Remove the resource endpoint, UI section, probe settings, and Compose probe
environment together. The existing runtime overview remains available. Do not
remove infrastructure services, ports, credentials, or named volumes.
