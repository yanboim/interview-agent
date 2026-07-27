# Modular API composition

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-004
- Product contract: `modular-api-composition`

## Objective

Turn `app/main.py` into a composition root that creates runtime dependencies,
installs middleware, mounts static assets, and includes domain routers. Move
DTOs, authorization helpers, transport utilities, and route handlers into
explicit API modules without changing public behavior.

## Non-goals

- Change endpoint paths or response contracts.
- Convert synchronous SQLAlchemy to async (TD-005).
- Introduce a general provider gateway (TD-007).
- Reorganize infrastructure adapters into a new package.
- Remove every compatibility import in one release.

## Acceptance criteria

- DTOs live outside the composition root.
- Authentication/authorization helpers do not import `app.main`.
- Auth, profile, administration, chat, conversations, interviews, and learning
  routes are registered through domain `APIRouter` modules.
- Routers obtain dependencies through one configured runtime container and
  never import the composition root.
- `app/main.py` contains construction, middleware, static/lifecycle wiring, and
  router inclusion rather than domain route flows.
- Existing endpoints and OpenAPI paths remain compatible.
- Architecture tests prevent route modules from importing `app.main`, prevent
  new `@app` domain routes in the composition root, and enforce a reduced
  `main.py` size budget.
- Focused router and authorization tests pass.
- `make harness-check` passes.

## Implementation steps

1. Add API runtime, schemas, security, and agent-I/O utility modules.
2. Extract domain routers without changing endpoint behavior.
3. Rebuild `main.py` as wiring plus middleware and compatibility exports.
4. Update tests to patch the runtime boundary instead of module globals.
5. Add mechanical architecture checks and OpenAPI compatibility assertions.
6. Update architecture, product contract, reliability docs, and debt status.

## Progress

- [x] `main.py` responsibilities, route groups, test imports, global services,
      and architecture gates inspected.
- [x] Runtime and shared API modules complete.
- [x] Domain router extraction complete.
- [x] Focused tests pass: 29 tests across main, authorization, administration,
      chat lifecycle, and architecture.
- [x] Full Harness gate passes: 9 static checks; 121 backend tests passed with
      1 external-service test skipped; 10 frontend unit tests; type-check,
      production build, bundle budgets, and 10 Playwright scenarios passed.

## Decisions and findings

- A single `ApiRuntime` is configured by the composition root and read by
  routers. It makes process dependencies explicit without turning the container
  into a transaction or correctness boundary.
- Existing imports from `app.main` remain as narrow compatibility aliases and
  wrappers. FastAPI itself registers only the domain-router handlers.
- `app/main.py` fell from 2,139 to 337 lines. An architecture test enforces a
  400-line budget and rejects new `/api` route decorators in the composition
  root.
- The dependency-direction test now scans nested application packages, closing
  the prior gap where only `app/*.py` was inspected.

## Rollback

This is a code-organization change with no database migration. Rollback restores
the prior route registration module. Endpoint paths and persisted data are
unchanged.
