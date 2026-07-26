# Interview Agent repository guide

This file is the entry point for coding agents. It is a map and a set of
mandatory gates, not a complete manual.

## Read first

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) for system boundaries and dependency
   rules.
2. Read [docs/product-specs/feature-contract.json](docs/product-specs/feature-contract.json)
   for machine-verifiable product behavior.
3. For non-trivial work, read
   [docs/exec-plans/README.md](docs/exec-plans/README.md) and create or update an
   execution plan.
4. Check [docs/tech-debt-tracker.md](docs/tech-debt-tracker.md) before expanding
   an area with known debt.
5. Use [README.md](README.md) for setup, deployment, and operator commands.

The repository is the system of record. If implementation and documentation
disagree, verify behavior, update both in the same change, and record a design
decision when the disagreement is architectural.

## Repository map

- `app/`: FastAPI backend, agent orchestration, domain calculations, and
  infrastructure adapters.
- `frontend/`: Vue application, component tests, and Playwright E2E tests.
- `migrations/`: Alembic schema history. Production schema changes belong here.
- `scripts/`: ingestion, evaluation, backup, restore, migration, and worker
  entry points.
- `tests/`: backend unit, contract, migration, and integration tests.
- `eval/`: versioned RAG and agent evaluation datasets and reports.
- `monitoring/`: Prometheus, Grafana, OpenTelemetry, and alert configuration.
- `docs/`: product contracts, design records, execution plans, reliability,
  security, and generated references.

## Work loop

1. Rehydrate context from this guide, the architecture document, the relevant
   product contract, the active execution plan, and the current diff.
2. State the intended behavior and the narrowest acceptance criteria.
3. Make the smallest complete change. Do not mix unrelated cleanup.
4. Add or update tests and repository documentation with the implementation.
5. Run focused checks while iterating.
6. Run `make harness-check` before declaring a repository-wide change complete.
7. Update the execution plan and technical-debt tracker. Move completed plans
   into `docs/exec-plans/completed/`.

Do not mark a feature `passing` in the feature contract without an executable
verification reference.

## Architecture gates

- `app/main.py` is the current composition root and legacy route host. Do not
  add new business rules there; put them in an application/domain service and
  keep the route as an adapter.
- Pure calculation modules must not import FastAPI, SQLAlchemy, Redis, Qdrant,
  HTTP clients, or model SDKs. The enforced module list lives in
  `tests/test_architecture.py`.
- `app/database.py` defines schema metadata only. It must not depend on the API,
  agent, retrieval, or network layers.
- No application module may import `app.main`; dependencies flow toward domain
  code, never back toward the composition root.
- Database changes require an Alembic migration and migration tests.
- External model calls must remain behind the agent/interview/reranker
  adapters. New call sites require timeout, error, metric, and cost behavior.
- User-owned reads and writes must include server-resolved `user_id`.
- Write endpoints that can be retried must define idempotency or concurrency
  behavior in their product contract.
- Knowledge ingestion must preserve the currently serving collection until a
  replacement has passed validation.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the current exceptions and target
module boundaries.

## Safety rules

- Never commit `.env`, credentials, tokens, database dumps, or user data.
- Never expose private knowledge text through public search tools.
- Never delete or replace a Qdrant collection as an incidental test action.
- Restore operations are destructive only with explicit operator confirmation.
- Do not weaken authentication, authorization, CSP, audit, or secret scanning
  to make a test pass.
- Preserve user changes and unrelated work already present in the worktree.

## Verification

- Focused backend test: `pytest -q tests/<relevant_file>.py`
- Backend suite: `pytest -q`
- Frontend unit/type/build: `make frontend-check`
- Harness contracts and architecture: `make harness-static`
- Full local gate, including browser E2E: `make harness-check`
- External-service PostgreSQL checks require `TEST_POSTGRES_URL`.
- Live model and RAG evaluations are explicit cost-bearing operations; do not
  run them unless the task requires them and credentials are configured.

If a required check cannot run, report the exact missing dependency and the
checks that did run. Do not silently substitute a weaker verification.
