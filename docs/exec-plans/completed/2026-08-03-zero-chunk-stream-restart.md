# Zero-chunk model stream restart

- Status: completed
- Date: 2026-08-03
- Owner: repository maintainers

## Objective

Recover a chat model call when the provider accepts the request but its SSE body
fails before producing any chunk. Keep retries bounded, visible in budgets and
metrics, and prohibit automatic replay after any chunk has entered the Agent
runtime. Ensure Workflow V2 structured specialist answers are emitted by the
HTTP stream even when LangChain exposes them only in the final graph state.

## Non-goals

- Do not enable an unevaluated fallback model.
- Do not retry a partially emitted stream.
- Do not relax request token, cost, model-call, or wall-clock budgets.

## Incident evidence

- Production request `cb4ac661-b6e1-4d45-ac9f-8750f34c2ee0` received provider
  HTTP 200 responses but ended after 61.629 seconds as retryable
  `ModelGatewayError`.
- The final provider response headers preceded failure by about 47 seconds;
  `LLM_TIMEOUT_SECONDS` was 45 seconds.
- App, worker, PostgreSQL, Redis and Qdrant remained healthy. Embeddings had no
  errors. The failure was isolated to the knowledge model stream.

## Acceptance criteria

- Sync and async model streams restart at most the configured count when an
  attempt fails before yielding a chunk.
- Every restart claims another request-scoped model-call budget and records
  stable attempted/recovered/exhausted metrics.
- A stream that yielded any chunk is never restarted and never switched to a
  fallback model.
- Workflow V2 waits for each concurrent specialist's validated final state and
  emits the structured answer in deterministic route order.
- The setting is bounded and documented; contract and Chinese mirror agree.
- Focused tests and the complete Harness pass.
- A scanned immutable image is deployed and an isolated live production probe
  verifies successful generation without retaining test identities or turns.

## Work

- [x] Implement bounded zero-chunk restart policy in the model gateway.
- [x] Add sync/async, partial-stream, budget and metric regression coverage.
- [x] Update configuration, contract, design and operator documentation.
- [x] Run focused checks and `make harness-check`.
- [x] Build, scan, deploy, verify and record the release.

## Completion evidence

- Focused gateway, executor, lifecycle, use-case and architecture coverage:
  52 passed.
- Complete Harness: all Agent groups 1.0; 29 static/architecture checks; 341
  backend tests passed with 2 explicit external-service skips; 23 frontend unit
  tests; type, production build and bundle gates passed. The parallel Playwright
  launcher timed out waiting for its already-started local web server; the full
  suite then passed 28/28 with one worker.
- Immutable app/worker image:
  `sha256:9ad9269920778a09ba1273ff2c9efdb7cc468d70256980f26c3e88072f1cfd2c`.
  Fixed-digest Trivy scans reported zero HIGH/CRITICAL findings for both exported
  tar archives.
- Release `production-stream-resilience-answer-fix-20260803-9ad926992077-r9`
  passed authenticated readiness and an isolated live-model stream with the
  event sequence `token`, `sources`, `citations`, `done`. Exact identity cleanup
  verified users, tokens, conversations, turns, messages, traces, tool audits,
  product events and request audits were all zero.
- The earlier r8 candidate was rejected and recorded as `failed` after its live
  probe exposed the missing structured-answer token; it was never recorded as a
  successful release.

## Rollback

No migration is required. Rollback restores the previous immutable app/worker
image together; existing failed turns remain safely retryable.
