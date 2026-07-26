# Durable chat-turn lifecycle

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-003
- Product contract: `durable-chat-turn-lifecycle`

## Objective

Give normal and streaming chat requests a durable turn identity and lifecycle,
prevent overlapping generation in one conversation, atomically materialize
completed user/assistant messages, and make failed or disconnected turns
explicitly retryable.

## Non-goals

- Add token-budgeted history or summaries (TD-008).
- Introduce a general model gateway (TD-007).
- Resume generation from an exact provider token offset.
- Migrate legacy message pairs into synthetic chat-turn rows.
- Refactor unrelated routes out of `app/main.py` (TD-004).

## Acceptance criteria

- `chat_turns` stores a durable turn ID, session sequence, idempotency key,
  request digest, lifecycle, owner token, partial/final answer, metadata, and
  failure detail.
- Each conversation has at most one active generating turn, enforced by a
  database conditional update rather than a process lock.
- Normal and streaming endpoints require `Idempotency-Key`.
- A completed same-key retry returns the stored response without another model
  call.
- A concurrent request in the same session is rejected before model invocation.
- User and assistant history messages are inserted together only when a claim
  completes successfully.
- Provider failure marks the turn failed and releases the session for retry.
- Streaming cancellation marks the turn cancelled, retains partial output for
  diagnosis, and allows the same command to retry.
- Message history contains only completed turns in deterministic order.
- Schema changes include Alembic migration and migration/data-copy tests.
- `make harness-check` passes.

## Implementation steps

1. Add conversation sequence/active fields and the `chat_turns` table.
2. Add storage operations to begin, complete, fail, and cancel a turn.
3. Add a chat lifecycle application service and remove eager user-message
   persistence.
4. Adapt normal and streaming routes, including completed response replay.
5. Retain and forward idempotency keys in the Vue chat store.
6. Add concurrency, replay, failure, cancellation, ordering, API, migration,
   and frontend tests.
7. Update architecture, contracts, reliability docs, and debt status.

## Progress

- [x] Normal/streaming routes, message schema, storage, frontend abort behavior,
      migrations, and data-copy script inspected.
- [x] Design and migration complete.
- [x] Focused tests pass: 35 backend tests plus 10 frontend unit tests.
- [x] Full Harness gate passes: static contracts 7 passed; backend 119 passed
      and 1 skipped; frontend type-check, 10 unit tests, production build, and
      bundle budgets passed; Playwright 10 passed.

## Rollback

The downgrade drops `chat_turns` and the two conversation coordination fields.
Completed messages remain in the existing table, so successful chat history is
preserved. Application rollback must accompany schema downgrade because the new
routes require lifecycle storage.
