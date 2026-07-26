# Testing and verification

## Verification levels

Choose the smallest check that proves the change while iterating, then run the
gate required by its scope.

| Scope | Command | Covers |
|---|---|---|
| One backend area | `pytest -q tests/<relevant_file>.py` | Focused Python behavior |
| Architecture or documentation | `make harness-static` | Dependency rules, feature contract, required docs, internal links |
| Backend repository | `make backend-check` | Compilation and backend suite |
| Frontend repository | `make frontend-check` | Type-check, unit tests, production build, bundle budget |
| Browser acceptance | `make e2e` | Playwright product flows |
| Repository-wide change | `make harness-check` | All checks above |

The CI workflow also performs dependency audits, builds the container image,
and scans it for high and critical vulnerabilities.

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

## Reporting results

Record:

- the exact command;
- pass, fail, or skip counts where available;
- external services or credentials that were unavailable;
- whether a weaker focused check ran in place of a required gate.

Do not describe an unrun check as passing, and do not silently substitute a
SQLite check for required PostgreSQL verification.
