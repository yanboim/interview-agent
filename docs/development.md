# Development guide

## Prerequisites

- Python 3.11 or newer
- Node.js 20 and npm
- Docker with Compose
- A Zhipu API key only for live model calls
- A Zhipu standard API key for live embedding or ingestion

The default automated test suites do not require live model credentials.
PostgreSQL integration tests require `TEST_POSTGRES_URL`; live Qdrant and model
evaluations are explicit because they need services or incur cost.

## Local setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci --prefix frontend
cp .env.example .env
```

Keep `.env` local. For a minimal application run, configure the required model
key, start dependencies, apply migrations, ingest knowledge, and run the API:

```bash
docker compose up -d postgres redis qdrant
alembic upgrade head
python -m scripts.ingest
uvicorn app.main:app --reload --port 8000
```

For frontend development in a second terminal:

```bash
npm --prefix frontend run dev
```

The complete Compose topology and operator commands are documented in the
[root README](../README.md). Configuration names and safe placeholder values
live in [`.env.example`](../.env.example).

## Repository boundaries

- `app/main.py` is the composition root and legacy route host. Put new business
  rules in application or domain services and keep routes as adapters.
- Pure calculations must not import FastAPI, SQLAlchemy, Redis, Qdrant, HTTP
  clients, or model SDKs.
- `app/database.py` defines schema metadata and does not depend on API, agent,
  retrieval, or network layers.
- Database schema changes require an Alembic migration and migration tests.
- User-owned data access uses the authenticated server-resolved `user_id`.
- External model calls stay behind the existing adapters and define timeout,
  error, metric, and cost behavior.

Read [ARCHITECTURE.md](../ARCHITECTURE.md) before changing dependencies or
correctness boundaries.

## Change workflow

1. Read `AGENTS.md`, the architecture, relevant feature contract, active plan,
   technical-debt entry, and current worktree changes.
2. State the intended behavior and narrow acceptance criteria.
3. For non-trivial work, create or update an
   [execution plan](exec-plans/README.md).
4. Make the smallest complete change and preserve unrelated work.
5. Update tests, product contracts, design records, operations, and security
   documentation in the same change where applicable.
6. Run focused checks while iterating, then the required repository gate.
7. Record verification in the plan and move completed plans to `completed/`.

Do not mark a feature `passing` without an executable verification reference.
Do not run live model or RAG evaluations unless the task requires them and the
required credentials and data-handling approval are in place.

## Database changes

Create a revision under `migrations/versions/`, update storage behavior, and add
tests that cover both the schema and the use case. Validate at least:

```bash
alembic upgrade head
pytest -q tests/test_migrations.py
```

Use `TEST_POSTGRES_URL` for PostgreSQL-specific behavior. Runtime `create_all`
is for local and isolated tests only; production schema evolution belongs to
Alembic.

## Before handoff

Run the verification appropriate to the change using the
[testing guide](testing.md). Repository-wide behavior changes require:

```bash
make harness-check
```

If a required check cannot run, report the exact missing dependency and list
the checks that did run.
