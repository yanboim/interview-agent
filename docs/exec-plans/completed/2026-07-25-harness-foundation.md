# Harness foundation

- Status: completed
- Date: 2026-07-25
- Owner: repository maintainers

## Objective

Make repository context, architectural constraints, acceptance contracts, and
verification commands directly legible and mechanically checkable by coding
agents.

## Non-goals

- Refactor the 2,000-line API composition module.
- Change production behavior or database schema.
- Resolve the P0 consistency and knowledge-publication debt.

## Acceptance criteria

- A root `AGENTS.md` maps repository knowledge and mandatory work gates.
- `ARCHITECTURE.md` defines boundaries, correctness rules, and known
  exceptions.
- Structured execution-plan and technical-debt locations exist.
- CI explicitly runs the harness static gate.
- Architecture tests enforce dependency and contract invariants.
- `make harness-check` runs the canonical backend, frontend, build, and E2E
  verification sequence.

## Decisions

- Existing GitHub Actions and Playwright coverage are extended rather than
  replaced.
- Playwright uses a process-isolated SQLite database by default. Reusing a
  fixed `/tmp` database allowed stale schemas to make local E2E results
  order-dependent.
- Architecture checks enforce boundaries that are true today and prevent new
  coupling. Existing monolith debt is documented instead of grandfathering a
  misleading target architecture as already complete.
- Live model, Qdrant, and PostgreSQL integration evaluations remain explicit
  because they require credentials or external services.

## Verification

`make harness-check` passed on 2026-07-25:

- Harness architecture and contract checks: 6 passed.
- Backend suite: 87 passed, 1 external-service test skipped.
- Frontend unit suite: 8 passed.
- Frontend type-check, production build, and bundle budgets: passed.
- Playwright desktop/mobile acceptance suite: 8 passed.

Individual checks are documented in `AGENTS.md` and the root `Makefile`.
