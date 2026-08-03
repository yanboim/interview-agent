# Testing and verification

## Verification levels

Choose the smallest check that proves the change while iterating, then run the
gate required by its scope.

| Scope | Command | Covers |
|---|---|---|
| One backend area | `pytest -q tests/<relevant_file>.py` | Focused Python behavior |
| Local iteration | `make dev-check` | Compilation, architecture, toolchain baseline, and frontend types |
| Architecture or documentation | `make harness-static` | Dependency rules, feature contract, required docs, internal links |
| Backend repository | `make backend-check` | Compilation and backend suite |
| Backend without services | `make backend-fast-check` | Compilation and tests not marked `integration` |
| Frontend repository | `make frontend-check` | Toolchain baseline, type-check, unit tests, production build, bundle budget |
| Browser acceptance | `make e2e` | Playwright product flows |
| Pull request | `make pr-check` | Deterministic repository, backend, frontend, build, bundle, and fresh migration checks |
| Main or release candidate | `make harness-check` | Complete checks above, including browser acceptance |

Fast branch and pull-request CI runs `make pr-check` in one job and cancels
superseded runs for the same branch. Main, nightly, and manual deep verification
adds browser acceptance, Python/npm dependency audits, a container build, and a
high/critical vulnerability scan. Release verification independently runs the
complete Harness against the exact tagged source.

## Isolation from operator configuration

Repository tests are safe to run from a production operator checkout. During
Pytest collection, `tests/conftest.py` overrides credentials, authentication,
rollout, telemetry, and persistence with hermetic values before application
modules are imported. Playwright starts its server with the same external-call
and API-key isolation plus a process-specific SQLite database. A test that needs
an external service must opt in explicitly through its documented `TEST_*`
variable; the default Harness must never inherit production Secrets or make a
live model call.

## External and cost-bearing checks

These checks are intentionally outside the default local gate:

- PostgreSQL-specific tests require `TEST_POSTGRES_URL`.
- Live Qdrant checks require a disposable or explicitly approved target.
- `python -m scripts.evaluate_rag` uses the configured embedding/retrieval
  services.
- `python -m scripts.evaluate_chunks --llm-rerank` sends candidate private
  knowledge text to the configured model provider and incurs model cost.
- `python -m scripts.evaluate_answers` evaluates the versioned answer-quality
  dataset.

Never point tests at a serving Qdrant collection if they can delete or replace
it. Never send private knowledge to a public search or model service without
confirming that the data is approved for that provider.

## Product contract evidence

`docs/product-specs/feature-contract.json` lists product behavior as either
`passing` or `planned`.

- A `passing` feature has at least one repository verification reference.
- A `planned` feature links to a concrete gap, normally the technical-debt
  tracker.
- A file's existence is only the traceability floor; its test must execute the
  behavior claimed by the feature.

When changing a feature, update its steps and evidence in the same change.

## Keeping output concise

Successful backend and frontend test runs use quiet or dot reporters. Browser
HTML and trace artifacts are uploaded only when deep verification fails. Prefer
the smallest focused check while iterating; do not paste a complete successful
CI log when the command and result summary are sufficient.

## Reporting results

Record:

- the exact command;
- pass, fail, or skip counts where available;
- external services or credentials that were unavailable;
- whether a weaker focused check ran in place of a required gate.

Do not describe an unrun check as passing, and do not silently substitute a
SQLite check for required PostgreSQL verification.

## Backend test taxonomy

New tests use the taxonomy documented in [`tests/README.md`](../tests/README.md):
unit, application, contract, integration, architecture, migration, and explicit
fault injection. Existing flat test paths remain supported while files move only
when their implementation area is already being changed.
