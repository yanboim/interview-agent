# Tiered verification gates

- Status: completed
- Date: 2026-08-03
- Owner: repository maintainers

## Objective

Shorten developer and pull-request feedback while preserving the complete
release safety gate. Reduce duplicate dependency installation, browser/image
work, repeated CI runs, and verbose successful-test output.

## Non-goals

- Do not weaken authentication, authorization, migration, architecture, or
  release verification.
- Do not remove the canonical `make harness-check` release gate.
- Do not add a third-party changed-file action or another runtime dependency.

## Acceptance criteria

- `make dev-check` provides a short compile, architecture, and frontend static
  feedback loop without starting services or browsers.
- `make pr-check` runs deterministic repository, backend, frontend, build, and
  migration checks without Playwright, dependency audits, or image builds.
- Branch and pull-request CI uses `make pr-check`, cancels superseded runs, and
  does not duplicate heavyweight deep checks.
- Main, scheduled, and manually dispatched deep verification retains the full
  Harness, dependency audits, image build, and high/critical image scan.
- Release packaging still depends on the complete Harness.
- CI reporters remain concise on success and retain failure artifacts.
- Executable workflow contracts and synchronized documentation describe the
  three verification levels.

## Work

- [x] Add local development and pull-request Make targets.
- [x] Split fast CI from deep verification and cancel superseded runs.
- [x] Add executable workflow regression coverage.
- [x] Update product contract and developer/testing documentation.
- [x] Regenerate documentation mirrors and run focused checks.
- [x] Run the complete Harness and archive this plan.

## Decisions

- Fast PR verification keeps all hermetic backend tests and the full frontend
  type/unit/build/bundle gate. Only browser, supply-chain, and image work moves
  to main/nightly/manual deep verification.
- A fresh SQLite migration remains in the PR gate because schema drift should
  fail before merge.
- Main remains protected by the full Harness; release independently reruns the
  canonical Harness against the exact tagged source.

## Rollback

No runtime or schema migration is involved. Reverting the Makefile, workflow,
contract-test, and documentation changes restores the previous CI behavior.

## Verification evidence

- `make dev-check`: 15 architecture tests passed in 12.64 seconds total.
- `make pr-check`: 30 static/contract tests, 342 hermetic backend tests, 23
  frontend tests, production build, bundle budget, and fresh 21-revision SQLite
  migration passed in 46.80 seconds before the final output optimizations.
- `make migration-check`: passed with one-line successful output.
- `make docs-check`: generated references and 123-document Chinese mirror passed.
- `make harness-check`: 30 static/contract tests, 342 backend tests with 2
  environment-gated skips, 23 frontend tests, production build/bundle gate, and
  28 Playwright tests passed in 72.66 seconds. The first sandboxed browser run
  could not connect to its local Uvicorn namespace; the complete gate passed
  outside that network isolation.
