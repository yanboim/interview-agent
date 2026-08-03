# Merge outstanding dependency branches

## Objective

Merge every remote branch whose commits are not already reachable from `main`,
preserving the repository's reproducible dependency inputs and complete main
verification gate.

## Non-goals

- Do not delete remote branches.
- Do not change product behavior beyond the dependency and build-tool updates
  already present on those branches.
- Do not run live-model or cost-bearing evaluations.

## Acceptance criteria

- Every remote branch present at the start of this work is reachable from
  `main`.
- Dependency locks, immutable build inputs, generated documentation, and the
  Simplified Chinese mirror remain current.
- `make harness-check` passes on the merged tree.
- The verified merge commit is pushed to remote `main` and its GitHub Actions
  run completes successfully.

## Contracts and architecture rules

- Preserve the `reproducible-build-inputs` and `tiered-verification-gates`
  feature contracts.
- Keep external images and dependency inputs immutable and mechanically
  verifiable.
- Preserve all user-owned work and never stage secrets or generated test
  artifacts.

## Steps and progress

- [x] Fetch and inventory all remote branches.
- [x] Identify branches not already reachable from `main`.
- [x] Merge the outstanding branches and resolve overlaps conservatively.
- [x] Regenerate dependency locks or documentation if required.
- [x] Run focused checks and `make harness-check`.
- [x] Record evidence, move this plan to `completed/`, commit, and push `main`.
- [x] Confirm the remote GitHub Actions run succeeds.

## Decisions and findings

- The two `agent/*` branches were already reachable from `main`.
- Twelve outstanding branches were Dependabot updates affecting Docker base
  images, GitHub Actions, and Python dependency locks.
- Local `.git` metadata was unavailable, so a temporary bare repository under
  `/tmp` was used with the existing workspace as its work tree.
- After the first two merges refreshed the temporary index, Git exposed a
  substantial pre-existing August 1–3 workspace delta that the initial
  timestamp-based status check had misclassified as clean. That work was
  preserved in a dedicated commit before merging overlapping branches.
- The first remote Deep verification exposed a clean-runner ordering defect:
  backend SPA route tests ran before `frontend/dist` existed. The canonical
  Make targets now make both backend suites depend on the shared
  `frontend-build` target, so the requirement holds locally, in PR checks, and
  on main even under parallel Make execution.

## Verification evidence

- `make pr-check`: passed; 30 static/contract tests, 343 backend tests, 25
  frontend tests, production build, bundle budget, and fresh SQLite migration.
- `make harness-check`: passed after the clean-runner ordering fix; 30
  static/contract tests, 343 backend tests with 2 skips, 25 frontend tests, and
  30 Playwright tests.
- Initial remote Deep verification run `30824650944`: image and dependency
  audit passed; Harness failed only because the frontend build followed the
  backend suite. This failure supplied the clean-runner regression evidence.
- Corrected remote Deep verification run `30826124485`: Harness, immutable
  image build and Trivy scan, Python dependency audit, and npm dependency audit
  all passed.

## Rollback

Revert the merge and follow-up commits through new reviewed commits; do not
rewrite shared `main` history. The pre-merge remote baseline was
`914036cb32b19e1f8c7a14562dd7bad650542fe2`.
