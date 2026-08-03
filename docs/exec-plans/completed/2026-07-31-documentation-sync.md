# Documentation synchronization

- Status: completed
- Date: 2026-07-31
- Completed: 2026-08-01
- Owner: repository maintainers

## Objective

Synchronize the current lifecycle documentation and Simplified Chinese mirror
with the Agent safety, grounding, personalized memory, durable workflow,
feedback-learning, and model-routing capabilities completed on 2026-07-31.

## Non-goals

- Change runtime behavior, schemas, feature status, or deployment state.
- Rewrite historical completed plans.
- Run live model, RAG, or cost-bearing evaluations.

## Acceptance criteria

- README, PRD, feature map, journeys, UX, glossary, metrics, and traceability
  cover all six new passing Agent contracts.
- Domain, data, component, security, operations, and quality documents describe
  the new ownership, confirmation, memory, run, feedback, evaluation, and
  routing boundaries.
- The onboarding guide and Agent engineering course are included in the
  lifecycle manifest and Chinese mirror.
- Generated references and Chinese documents are current; internal links,
  static contracts, and the full repository gate pass.

## Progress

- [x] Current implementation, migrations 0017–0021, feature contracts,
      completed hardening plan, and documentation drift inventoried.
- [x] Product and UX documentation synchronized.
- [x] Architecture, security, operations, and quality documentation synchronized.
- [x] Lifecycle manifest and Chinese mirror synchronized (120 documents).
- [x] Deterministic, backend, frontend, browser, and documentation gates passed.

## Verification

- `make docs-generate`: passed; generated references and the 120-document
  Simplified Chinese mirror were refreshed.
- `make harness-static`: passed; all five Agent evaluation groups scored 1.0
  and 18 architecture/documentation contract tests passed.
- `make harness-check`: passed on 2026-08-01 with 279 backend tests (2 optional
  skips), 22 frontend unit tests, production build and bundle gates, and 28
  browser end-to-end tests.

## Rollback

Restore the prior lifecycle documents and mirror lock. No runtime, schema, or
user-data rollback is required.
