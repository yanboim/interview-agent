# Release Harness gate alignment

- Status: completed
- Date: 2026-08-01
- Owner: repository maintainers

## Objective

Require the exact release source revision to pass the canonical repository
Harness before a Canary or production image artifact can be packaged.

## Non-goals

- Deploy an artifact automatically.
- Change environment approval, migration, rollback, or release-ledger behavior.
- Run live model or RAG evaluations.
- Change application runtime behavior.

## Acceptance criteria

- Release verification runs `make harness-check` after installing its locked
  Python, Node, and Chromium dependencies.
- Artifact packaging is a separate job with a mechanical dependency on the
  successful Harness job.
- Canary or production environment approval applies to packaging after source
  verification succeeds.
- A repository contract test prevents release packaging from bypassing the
  canonical Harness.
- Release documentation and its Simplified Chinese mirror describe the actual
  gate.

## Implementation

1. Split the Release workflow into `verify-harness` and `package` jobs.
2. Run the canonical Harness in the verification job.
3. Bind packaging to verification with `needs: verify-harness`.
4. Add a static workflow contract and update release documentation.

## Progress

- [x] Existing CI, Release workflow, Harness target, and release documentation
      inspected.
- [x] Release verification and packaging jobs separated.
- [x] Packaging mechanically bound to the complete Harness.
- [x] Workflow contract and release documentation updated.
- [x] Focused tests, documentation generation, static Harness, and complete
      Harness verification recorded.

## Verification

- `pytest -q tests/test_harness_contract.py`: 7 passed.
- `make docs-generate`: 120 documents generated and mirrored.
- `make harness-static`: 18 tests passed; documentation, architecture, product
  contracts, and all five Agent evaluation groups passed.
- `make harness-check`: 279 backend tests passed with 2 skipped, 22 frontend
  unit tests passed, frontend type/build/bundle checks passed, and 28 browser
  end-to-end tests passed.

## Rollback

Restore the previous single release job. No application, database, migration,
user-data, or deployed-environment rollback is required.
