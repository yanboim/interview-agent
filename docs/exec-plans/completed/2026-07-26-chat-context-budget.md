# Token-budgeted chat context

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-008
- Product contract: `token-budgeted-chat-context`

## Objective

Bound every chat request by a configured context token budget while retaining
recent completed messages and a durable, incrementally advanced summary of
older messages.

## Non-goals

- Change prompts, providers, or model selection.
- Delete compacted messages from conversation history.
- Use a cost-bearing model call to produce the summary.
- Summarize pending, failed, or cancelled turns.

## Acceptance criteria

- Context calculation is deterministic, provider-independent, and unit tested.
- The current request, summary, and recent history stay within the configured
  token budget.
- Oversized current requests fail before a turn is claimed.
- Summary text and its covered message ID are persisted on the conversation.
- Summary advancement and turn claim occur in one database transaction.
- Retried turns do not summarize the same messages again.
- SQLite migration/head and durable reconstruction tests pass.
- `make harness-check` passes.

## Progress

- [x] Existing chat lifecycle, schema, and migration head inspected.
- [x] Pure context planner and settings implemented.
- [x] Durable summary schema and migration implemented.
- [x] Turn claim integrated with bounded context.
- [x] Truncation, retry, migration, and route tests pass.
- [x] Full Harness and documentation closeout complete.

## Decisions

- Token estimates use a conservative UTF-8 byte upper bound plus per-message
  framing overhead. This remains deterministic without coupling domain code to
  one provider tokenizer.
- Stored messages remain the audit/history source of truth. Compaction changes
  model input only.
- Summary generation is deterministic and bounded, avoiding an extra external
  model call in the correctness-critical claim transaction.

## Verification

- Focused context, lifecycle, migration, architecture, and data migration
  checks: 32 passed.
- Full backend suite: 144 passed, 2 optional external-service checks skipped.
- `make harness-check`: static/compile/backend, frontend unit/type/build/bundle,
  and 10 Playwright scenarios passed.

## Findings

- The current request is validated before conversation creation or durable turn
  claim, so a `413` response leaves no lifecycle residue.
- Compaction retains complete recent user/assistant turns when possible and
  never deletes the original message rows.
- A retry reads only message IDs beyond the durable marker, preventing summary
  duplication.

## Rollback

The migration adds nullable/defaulted conversation columns and can be
downgraded without changing stored messages. Application rollback ignores the
new columns.
