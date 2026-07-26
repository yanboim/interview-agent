# Durable chat-turn lifecycle

## Context

The original chat path persisted a user message before invoking the model and
persisted the assistant message only after success. Failures and client
disconnects left orphan user messages. Concurrent requests could read the same
history and both invoke the model, producing nondeterministic ordering.

## Decision

Add `chat_turns` as the command/workflow record. A turn contains:

- durable `turn_id` and per-session `turn_index`;
- client `idempotency_key` and request digest/content;
- `pending`, `generating`, `completed`, `failed`, or `cancelled` state;
- claim-owner token, partial/final assistant content, metadata, error, and
  timestamps.

Each conversation stores `next_chat_turn_index` and `active_chat_turn_id`.
Beginning a command conditionally sets the active turn only when it is null and
increments the sequence in the same transaction. This serializes model calls
per session across application replicas without a Python lock.

A new turn transitions from `pending` to `generating` before the transaction
commits. On success, the owned claim becomes `completed`, the user and assistant
messages are inserted together, and the active slot is released in one
transaction. Failed and cancelled turns are retained but do not appear in
message history.

## Retry outcomes

- Same completed key and content: replay the stored answer and metadata.
- Same key while generating: return a retryable conflict.
- Same failed/cancelled key and content: reclaim the same turn and sequence.
- Same key with different content: reject key misuse.
- Different key while a session is generating: reject before model invocation.
- New key after a terminal failure: allocate the next logical turn.

## Streaming disconnect

The server catches generator cancellation separately from ordinary exceptions,
stores the accumulated partial answer as `cancelled`, releases the conversation
active slot, then propagates cancellation. A retry regenerates the answer from
the start; exact provider-token continuation is outside this change.

## Compatibility

Legacy completed messages remain readable and are used as model context.
Migration initializes each conversation's next sequence from its count of
legacy user messages plus one. It does not synthesize lifecycle rows for old
history.
