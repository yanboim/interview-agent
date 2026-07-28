# Administrator observability and audit

- Status: completed
- Date: 2026-07-28
- Owner: repository maintainers

## Objective

Remove the administrator black box with three linked views:

1. authoritative server-side activity audit;
2. canonical user-input/system-output interaction records;
3. request-correlated execution traces for agents, tools, and outcomes.

## Non-goals

- Copy chat or interview content into generic audit rows.
- Store passwords, tokens, API keys, authorization headers, raw connection
  strings, or complete private knowledge chunks.
- Put user content in application logs, Prometheus labels, or OpenTelemetry
  attributes.
- Add arbitrary SQL, shell, or infrastructure control to the administrator UI.

## Acceptance criteria

- Authenticated API activity is recorded server-side with actor, action,
  request ID, route, outcome, status, duration, and sanitized target metadata.
- Administrator interaction queries read canonical chat and interview tables
  and expose exact user input and persisted system output without duplicating
  content into audit storage.
- Chat/interview execution outcomes and tool calls can be correlated to an
  interaction and request ID.
- Administrator content reads are themselves audit events.
- Administrator APIs support bounded filters and never return credentials,
  authorization headers, password fields, or raw infrastructure errors.
- The administrator UI supports activity filtering, interaction inspection,
  and an execution timeline.
- Alembic migration/rollback tests, backend/frontend tests, full Harness, and
  production migration/smoke verification pass.

## Implementation plan

1. Add `audit_events` and `execution_traces`, plus correlation columns on tool
   audits, through metadata and Alembic.
2. Add storage methods for sanitized writes, filtered activity reads, canonical
   interaction reads, and correlated trace reads.
3. Add authoritative HTTP audit middleware and chat/interview trace emission.
4. Add administrator APIs and replace the tool-only audit screen with an audit
   and interaction center.
5. Update product/architecture/operator documentation, run Harness, migrate,
   deploy, and verify with production data.

## Progress

- [x] Existing persistence, auth, audit, product-event, runtime, and UI
  boundaries inspected.
- [x] Schema and storage complete.
- [x] Request audit and execution tracing complete.
- [x] Administrator APIs and UI complete.
- [x] Verification and production deployment complete.

## Verification evidence

- Focused administrator observability, architecture, migration, frontend, and
  browser tests pass.
- `make harness-check` passes: 16 static checks, 186 backend tests with 2
  expected skips, 13 frontend unit tests, production frontend build, and 16
  browser project/test combinations.
- Production App image
  `sha256:ac1bdfe12825f9c7d75e01553cd6ac508e73440a4b040a80baf1f1fd8b6f574f`
  is healthy with zero restarts; PostgreSQL remains at Alembic head
  `20260728_0013`.
- A request through the production Nginx entry point to the protected
  interaction API returned 401 and produced the correlated, sanitized
  `denied` audit event.
- Production canonical reads found both chat and interview records with
  persisted input and output fields. No content was printed during deployment
  verification.
- A pre-deployment PostgreSQL custom-format backup is stored at
  `/tmp/interview-agent-pre-admin-audit-20260728.dump`, and the previous App
  image is tagged `interview-agent-app:rollback-admin-audit-20260728`.

## Security decisions

- Full content remains in its domain tables and is not copied into audit or
  tracing tables.
- Trace details contain identifiers, versions, counts, and source references,
  not credentials or full private knowledge text.
- Only the administrator surface can read cross-user interaction content.
- Every administrator interaction/trace read is captured by the HTTP audit
  middleware.

## Rollback

Restore the previous App image while retaining the additive observability
tables and nullable columns. Do not downgrade the production schema
independently because the later deployment-release migration depends on this
migration. Domain interaction records remain unchanged.
