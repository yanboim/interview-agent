# Interview answer idempotency

## Context

The original answer route read the pending turn, called the scorer, generated a
successor question, and only then wrote the answer. Concurrent requests could
therefore call both models before either request changed durable state.
Process-local locks cannot protect a multi-instance deployment.

## Decision

Use the existing `interview_turns.id` as the durable turn identity and add:

- `submission_status`: `pending`, `generating`, `completed`, or `failed`;
- `idempotency_key` and `answer_digest`;
- `claim_token`, identifying the request allowed to commit;
- `result_json`, containing the exact successful API response;
- `submission_error` and `processing_started_at` for diagnosis.

The API requires an `Idempotency-Key`. The application service first asks the
store to claim the current pending turn. The store performs a conditional
database update from `pending` (or the same failed command) to `generating`.
Only the winning claim may invoke models.

Completion conditionally updates the claimed turn and, in the same transaction,
inserts its answer attempt, optionally inserts one successor turn, updates the
interview status, and stores the response. A unique key scoped to the interview
prevents one command key from identifying two turns.

## Request outcomes

- New pending command: claim it and run the models.
- Same key and answer while generating: return a conflict/retry response; do not
  call a model.
- Different key while a turn is generating: return a conflict.
- Same completed key and answer: return `result_json` unchanged.
- Same key with different answer: reject as an idempotency misuse.
- Handled model failure: mark the owned claim `failed`; the same key and answer
  may claim it again.

No automatic lease takeover is used. Reclaiming a live-but-slow provider call
could violate the at-most-once model-call guarantee. A process crash can leave a
turn in `generating`; recovery is an explicit future operational concern.

## Consequences

- Idempotency protects initial answer submission, not the intentional re-score
  endpoint.
- Clients must retain the key across ambiguous failures.
- Old answered rows migrate to `completed`; old unanswered rows migrate to
  `pending`.
- The database, rather than a Python lock, decides the claim winner.
