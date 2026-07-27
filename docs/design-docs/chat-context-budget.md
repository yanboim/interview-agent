# Chat context budget and durable summary

## Boundary

Completed messages remain immutable in `messages`. The model context is a
derived view consisting of:

1. a bounded system summary of older completed messages;
2. the newest completed messages that fit;
3. the current user request.

`app/chat_context.py` owns the pure planning and estimation rules.
`ConversationStore.begin_chat_turn` owns transactional loading and persistence.

## Persistence

Each conversation stores:

- `chat_summary`: bounded deterministic summary text;
- `chat_summary_through_message_id`: the greatest message ID incorporated into
  that summary.

Only messages after the marker are considered for the next compaction.
Advancing the marker and claiming a turn happen in one transaction, so a
retry cannot duplicate already summarized messages. Pending input and partial
assistant output are never summarized.

## Budget behavior

The estimator uses UTF-8 byte length plus fixed message framing overhead. It is
intentionally conservative and independent of provider-specific tokenizers.
If complete history fits, it is passed through unchanged. Otherwise the
planner reserves a bounded summary allowance, retains the newest messages that
fit, and folds the older prefix into the durable summary.

The current request is always retained. A request that cannot fit by itself is
rejected before durable turn claim.
