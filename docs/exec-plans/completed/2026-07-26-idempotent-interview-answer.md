# Idempotent interview answer submission

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-002
- Product contract: `idempotent-interview-answer`

## Objective

Ensure that retries and concurrent submissions for one pending interview turn
can run scoring and successor-question generation at most once, persist one
answer attempt and one successor turn, and return the stored response to a safe
retry after completion.

## Non-goals

- Make answer re-scoring (`/turns/{turn_index}/retry`) idempotent.
- Introduce a general workflow engine or distributed job queue.
- Automatically reclaim a process that dies while it owns a model call.
- Refactor unrelated interview, reporting, or learning behavior.

## Acceptance criteria

- Every interview turn has a durable database identity and submission lifecycle.
- The client supplies an `Idempotency-Key` and reuses it after transport/server
  failure.
- A database conditional update permits one owner to move a pending turn to
  `generating`.
- Concurrent requests with the same or different keys do not run scoring twice.
- Reusing a key with different answer content is rejected.
- A completed retry returns the stored original response without model calls.
- Answer, attempt history, successor turn, interview status, and stored response
  commit in one transaction owned by the claim token.
- A handled model failure moves the claim to `failed`; only the same request key
  and answer may retry it.
- Schema changes ship through Alembic with migration tests.
- `make harness-check` passes.

## Implementation steps

1. Add submission lifecycle, idempotency, digest, claim, result, and error fields
   to `interview_turns`.
2. Add storage operations to claim, fail, and conditionally complete a turn.
3. Add an application service that owns the model-call workflow.
4. Keep the FastAPI route as an adapter and require `Idempotency-Key`.
5. Make the Vue store retain one key until the submission succeeds.
6. Add storage concurrency, service replay/failure, route, migration, and
   frontend API tests.
7. Update architecture, product contract, operator docs, and debt status.

## Progress

- [x] Current route, model calls, storage transaction, schema, migrations, and
      frontend submission flow inspected.
- [x] Design and migration complete.
- [x] Focused tests pass: 30 backend tests plus 10 frontend unit tests.
- [x] Full Harness gate passes: static contracts 7 passed; backend 109 passed
      and 1 skipped; frontend type-check, 10 unit tests, production build, and
      bundle budgets passed; Playwright 10 passed.

## Rollback

The migration downgrade removes only the new lifecycle columns and constraint.
The existing answer, scoring, attempt-history, and successor-turn fields remain
unchanged. Application rollback must be paired with migration downgrade because
the new route depends on lifecycle state.
