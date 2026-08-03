# Reliability and operations

This document describes the current operating model and safe first actions. The
[root README](../../README.md) remains the command-oriented quick start.

## Runtime dependencies

| Component | Role | Current failure behavior |
|---|---|---|
| FastAPI application | HTTP API and built frontend | Process failure removes that replica |
| PostgreSQL or SQLite | Durable users, sessions, interviews, learning, audits | Readiness fails when the configured database is unavailable |
| Redis | Shared rate limits, RAG cache, publication lock, job queue | Rate limiting falls back locally; publication fails closed when Redis is configured but unavailable |
| Qdrant | Versioned private knowledge index | Readiness and knowledge retrieval fail; the last published alias remains unchanged on failed ingestion |
| Zhipu APIs | Chat, interview, scoring, embeddings, optional reranking | The model gateway applies timeout, retry, concurrency, budget, safe errors, and metrics |
| Worker | Long-running knowledge ingestion | Process heartbeat plus owner-fenced Redis job leases, retries, crash recovery, and dead-lettering |

## Health and observation

- `GET /health` is process liveness.
- `GET /ready` checks required configured dependencies and should control
  traffic admission.
- `GET /metrics` exposes Prometheus-format application and dependency metrics.
- Structured JSON logs are controlled by `JSON_LOGS` and `LOG_LEVEL`.
- OpenTelemetry export is enabled with `OTEL_ENABLED` and the configured OTLP
  endpoint. The application exports both traces and low-cardinality operational
  metrics; the bundled Collector accepts both signals.
- Unknown dependency and provider exceptions are logged server-side and mapped
  to stable public messages. Readiness and administrator dependency summaries
  never include exception classes, internal URLs, credentials, or provider
  response text.

Prometheus and Grafana are included in Compose. Do not expose Qdrant, Redis,
PostgreSQL, Prometheus, Grafana, or the OpenTelemetry collector publicly.

## First-response runbook

1. Confirm scope: one request, one replica, or the whole service.
2. Check liveness and readiness separately:

   ```bash
   curl -fsS http://localhost:8000/health
   curl -fsS http://localhost:8000/ready
   docker compose ps
   ```

3. Inspect application and affected dependency logs without printing secrets or
   private knowledge:

   ```bash
   docker compose logs --since=15m app worker
   ```

4. Check Prometheus/Grafana for request errors, dependency errors, and latency.
5. If a deployment caused the incident, stop promotion and use the release
   rollback procedure. If a knowledge publication caused it, use the versioned
   knowledge rollback below.
6. Record the timeline, affected feature, mitigation, and follow-up debt or
   design work.

Do not delete collections, clear databases, rotate secrets, or run a confirmed
restore as a diagnostic shortcut.

### Recovering abandoned chat generation

After confirming that the prior application owner is stopped and a chat turn
has exceeded the approved incident threshold, preview the target database and
run the bounded recovery command:

```bash
python -m scripts.recover_stale_chat_turns --older-than-seconds 600 --limit 100 --confirm
```

The command is intentionally opt-in and refuses thresholds below 60 seconds.
It changes only matching over-age `generating` claims to `failed`, releases
their session ownership, and invalidates the old claim token. A retry with the
same idempotency key then reuses the turn under a new token. Record the command,
threshold, target environment, recovered count, and retry result. Never use it
while the previous replica may still be serving normal traffic.

Normal Workflow V2 request timeouts do not require this operator command: the
executor cancels sibling specialist tasks with a bounded drain and the use case
persists `failed`/`cancelled` before returning. The command remains only for a
process crash or a request that was already abandoned before the application
could run its terminal transition.

## Knowledge publication and rollback

Ingestion builds a versioned physical Qdrant collection, validates it, runs the
configured regression gate, and atomically moves a stable alias. A failed
candidate does not replace the serving version.

Inspect and roll back through authenticated administrator endpoints:

```text
GET  /api/admin/knowledge/status
POST /api/admin/knowledge/rollback
{"collection_name":"interview_knowledge__v_<version>"}
```

Rollback changes only the alias and does not delete the version being left.
Version retention is not automated; monitor Qdrant capacity and never manually
delete the collection currently targeted by the serving alias.

The accepted design is recorded in
[Qdrant versioned publication](../design-docs/qdrant-versioned-publication.md).

## Backup and restore

Production backup requires a PostgreSQL `DATABASE_URL` and a reachable Qdrant:

```bash
python -m scripts.backup --dry-run
python -m scripts.backup --output backups
```

The backup directory contains a PostgreSQL dump and a manifest with Qdrant
snapshot metadata. Validate a backup without changing the database:

```bash
python -m scripts.restore backups/<timestamp>
```

`--confirm` runs `pg_restore --clean` and overwrites the configured PostgreSQL
database. Use it only in an approved maintenance window after verifying the
target and backup:

```bash
python -m scripts.restore backups/<timestamp> --confirm
```

The restore script does not restore Qdrant automatically. Follow the snapshot
metadata in the manifest and confirm the target collection separately. A backup
is not proven until restore has been rehearsed in a non-production environment.

## Operational limits

The prioritized structural register is the
[technical-debt tracker](../tech-debt-tracker.md); its current entries are
completed. Residual operational limits still require explicit handling:

- a hard process crash can leave a chat or interview turn in `generating`;
  chat has bounded owner-fenced operator recovery, while automatic takeover is
  prohibited and interview recovery remains workflow-specific;
- Qdrant historical-version retention is not automated;
- formal RPO, RTO, data-retention periods, and capacity targets are not yet
  approved.

Detailed procedures now live in the [operations manual](../operations/README.md)
and [release runbooks](../release/README.md).
