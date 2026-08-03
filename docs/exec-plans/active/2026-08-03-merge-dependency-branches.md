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
- [ ] Merge the outstanding branches and resolve overlaps conservatively.
- [ ] Regenerate dependency locks or documentation if required.
- [ ] Run focused checks and `make harness-check`.
- [ ] Record evidence, move this plan to `completed/`, commit, and push `main`.
- [ ] Confirm the remote GitHub Actions run succeeds.

## Decisions and findings

- The two `agent/*` branches are already reachable from `main`.
- Twelve outstanding branches are Dependabot updates affecting Docker base
  images, GitHub Actions, and Python dependency locks.
- Local `.git` metadata is unavailable, so a temporary bare repository under
  `/tmp` is used with the existing clean workspace as its work tree.
- After the first two merges refreshed the temporary index, Git exposed a
  substantial pre-existing August 1–3 workspace delta that the initial
  timestamp-based status check had misclassified as clean. Preserve that work
  in a dedicated commit before merging branches that overlap its workflow and
  dependency files.

## Rollback

Before push, discard only the temporary merge commits and retain the remote
`main` SHA as the rollback point. After push, revert the merge commit through a
new reviewed commit; do not rewrite shared history.
