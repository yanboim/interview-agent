# Nginx unified gateway

- Status: completed
- Date: 2026-07-27
- Owner: repository maintainers

## Objective

Add a hardened Nginx reverse proxy as the single externally reachable HTTP
entry point for the Compose deployment while keeping the application operator
port and all infrastructure services restricted to loopback or the private
Compose network.

## Non-goals

- Invent a production domain or TLS certificate.
- Expose Grafana, Prometheus, PostgreSQL, Redis, Qdrant, or OpenTelemetry.
- Change application authentication, authorization, API routes, or schemas.
- Modify the parallel lifecycle-documentation work already present in the
  worktree.

## Acceptance criteria

- A digest-pinned official Nginx image listens publicly on the configurable
  gateway HTTP port and proxies requests to `app:8000`.
- The app operator port remains bound to `127.0.0.1`; infrastructure ports
  remain private or loopback-only.
- Forwarded client identity, protocol, host, upgrade, long-running response,
  and request-size behavior are explicit.
- `/metrics` is unavailable through the public gateway while application
  liveness, readiness, API, and frontend routes work.
- The gateway runs read-only with dropped capabilities, no-new-privileges,
  writable runtime tmpfs mounts, and a health check.
- Compose validation, Nginx syntax tests, focused gateway tests, the full
  Harness, and production smoke checks pass.

## Implementation plan

1. Add the pinned gateway service and explicit proxy-trust configuration.
2. Add a reviewable Nginx configuration and focused static contract tests.
3. Document access, TLS boundary, exposure rules, deployment, and rollback.
4. Run repository gates and deploy only the new/reconfigured edge services.
5. Verify public binding, routes, blocked metrics, logs, and unchanged
   application/dependency health.

## Progress

- [x] Existing ports, Compose services, security guidance, and parallel changes
  inventoried.
- [x] Port 80 and 443 confirmed available before implementation.
- [x] Gateway configuration and documentation implemented.
- [x] Static and full verification complete.
- [x] Production deployment and smoke verification complete.

## Decisions

- HTTP port 80 is enabled first so the server IP can be used immediately.
  HTTPS requires an operator-approved domain and certificate and must not be
  simulated with a self-signed production endpoint.
- The loopback app port remains available for local diagnosis and rollback, but
  is not externally reachable. All external traffic enters through Nginx.
- Application rate limiting needs the original client address, so Uvicorn is
  configured to trust forwarded headers inside the private Compose network.
- Because Nginx is the only public edge, it replaces rather than appends any
  client-supplied `X-Forwarded-For` value. This prevents callers from spoofing
  the address used by application rate limiting and audit behavior.

## Findings

- The first production start exposed a hardening/runtime mismatch before app
  reconfiguration: root Nginx attempted to `chown` its tmpfs cache after all
  capabilities had been dropped and restarted with exit code 1. The app
  remained healthy and reachable on its loopback port. The gateway now starts
  directly as the image's unprivileged UID/GID 101 with explicitly owned tmpfs
  mounts, retaining the read-only filesystem and full capability drop.

## Verification evidence

- `docker compose config --quiet` passed.
- Nginx syntax validation passed under the production-equivalent non-root,
  read-only, zero-capability configuration.
- Focused gateway and reproducibility tests passed: 6 tests.
- Final `make harness-check` passed: 16 static checks, 159 backend tests with 2
  optional external-service skips, 11 frontend unit tests, frontend
  type/build/bundle gates, and 10 Playwright tests.
- Gateway and app are healthy with zero restarts after the corrected
  deployment. Nginx is bound to `0.0.0.0:80`; app, PostgreSQL, Redis, Qdrant,
  Prometheus, and Grafana remain bound to `127.0.0.1`.
- Gateway `/health` and `/ready` returned 200, `/today` returned 200,
  `/metrics` returned 404, and anonymous `/api/auth/me` returned 401.
- Desktop 1440x900 and mobile 390x844 browser smoke loaded meaningful UI with
  no console, page, server, or horizontal-overflow issues.
- Direct access through `http://192.168.0.111/health` returned healthy.
- A request carrying spoofed `X-Forwarded-For: 203.0.113.55` reached the app
  as the actual Docker edge address `172.18.0.1`; the spoofed value was not
  trusted.
- Final gateway/app deployment-window logs contained no emerg, fatal,
  traceback, permission, or Nginx error records.

## Rollback

Stop and remove only the gateway container, then keep using the existing
loopback application port for local diagnosis. Revert the Compose/config
change before any future deployment. Do not remove application or dependency
volumes.
