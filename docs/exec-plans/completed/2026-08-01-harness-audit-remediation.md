# Harness audit remediation

- Status: completed
- Date: 2026-08-01
- Owner: repository maintainers

## Objective

Close the actionable findings from the 2026-08-01 Harness audit without
changing the established database, Redis lease/fencing, or LangGraph state
boundaries. Unknown infrastructure and provider exceptions must never be
returned to clients, and core request, dependency, model, token, cost, and
product metrics must have an OTLP export path suitable for aggregation across
application instances.

## Non-goals

- Replace the fixed Redis Lua scripts used for atomic queue transitions.
- Add a LangGraph checkpointer to ordinary chat turns or replace the
  application-owned `agent_runs`/`agent_steps` state machine.
- Automatically take over a model call that may still be running under an old
  owner token.
- Change domain-validation messages intentionally returned for controlled
  authentication, conflict, not-found, payload-size, or validation errors.
- Run live or cost-bearing model and RAG evaluations.

## Acceptance criteria

- Generic readiness, interview, administration, queue, and knowledge failures
  return stable public messages that contain no exception text; complete
  exceptions remain in server logs.
- Administrator dependency summaries expose a stable health state without
  exception class names, URLs, credentials, or provider messages.
- Core operational metrics are emitted through OpenTelemetry instruments while
  the existing `/metrics` and local administrator snapshot remain compatible.
- The bundled Collector accepts the metrics signal as well as traces.
- Regression tests inject secret-shaped exception text and prove it is absent
  from API responses and administrator runtime summaries.
- Existing owner fencing, stale-step recovery, untrusted-evidence wrapping,
  audit metadata allowlisting, and deterministic Agent evaluation remain
  passing.

## Implementation

1. Introduce stable public error constants and apply them only to unknown
   internal exceptions.
2. Add OpenTelemetry counters, histograms, and up/down counters behind the
   existing `RequestMetrics` adapter.
3. Configure OTLP metric export and the Collector metrics pipeline.
4. Add focused API and metrics tests, update the feature contract and generated
   documentation, then run the canonical Harness gate.

## Verification

- Focused error-redaction and operations/telemetry tests.
- Existing chat, interview, administration, tool-safety, worker, and Agent-run
  recovery tests.
- `make harness-static`
- `make harness-check`

## Progress

- [x] Stable public error mapping implemented for unknown readiness, interview,
  administration, queue, and knowledge failures.
- [x] Administrator dependency summaries reduced to stable health metadata.
- [x] Core metrics mirrored to OTel instruments and the Collector metrics
  pipeline enabled.
- [x] Focused error-redaction and OTel metrics tests pass (6 tests).
- [x] Product contract and generated references are current; the 120-document
  Simplified Chinese mirror passes its lock check.
- [x] Focused regression: 88 tests passed.
- [x] Static Harness: 17 tests passed; all five deterministic Agent evaluation
  groups passed at 100%.
- [x] Backend suite: 278 passed, 2 optional external-service tests skipped.
- [x] Frontend toolchain/type checks, 22 unit tests, production build, and
  bundle budgets passed.
- [x] Playwright: 28 browser tests passed after rerunning outside the local
  network sandbox. The first sandboxed attempt could not reach its own local
  web server and timed out before test execution.

## Rollback

Revert the public-error constants, OTel instrument calls, metrics exporter, and
Collector metrics pipeline together. No migration or persistent-data rollback
is required.
