# Per-worktree stack isolation

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-009
- Product contract: `worktree-stack-isolation`

## Objective

Allow two repository worktrees to run their Compose stacks and browser gates at
the same time without container, volume, network, or host-port collisions.

## Non-goals

- Change internal container service names or ports.
- Provision remote shared environments.
- Automatically start or destroy containers during normal tests.

## Acceptance criteria

- Compose contains no fixed `container_name`.
- Every published host port is parameterized while internal ports stay stable.
- A deterministic generator derives a safe project suffix and non-overlapping
  host-port block from the resolved worktree path.
- Stack commands consume the generated environment without shell evaluation.
- Playwright uses the generated per-worktree port.
- Tests prove deterministic same-worktree output and distinct two-worktree
  project/resource/port values.
- Documentation includes start, inspect, and teardown commands.
- `make harness-check` passes.

## Progress

- [x] Fixed names, published ports, and E2E port inventoried.
- [x] Worktree environment generator implemented.
- [x] Compose and Playwright parameterized.
- [x] Make targets and operator documentation implemented.
- [x] Isolation tests and full Harness pass.

## Decisions

- Compose project names are the namespace boundary for containers, networks,
  and named volumes.
- Host ports use a deterministic block selected from the resolved absolute
  worktree path; explicit environment overrides remain supported.
- The generated `.env.worktree` is local state and must not be committed.

## Verification

- Worktree generator and repository contracts: 17 passed during focused
  iteration.
- Full backend suite: 151 passed, 2 optional external-service checks skipped.
- `docker compose ... config --quiet`: generated project configuration parsed
  successfully without starting containers.
- `make harness-check`: frontend unit/type/build/bundle and all 10 Playwright
  scenarios passed on generated port 38917.

## Findings

- Removing `container_name` restores Compose's native project prefix for every
  container, network, and named volume.
- Internal service discovery remains unchanged, so no application runtime URL
  needed to vary by worktree.
- The generator writes no credentials and atomically replaces only the ignored
  `.env.worktree` file.

## Rollback

Default port values preserve the existing single-worktree commands. Rolling
back removes generated stack targets and restores fixed Compose naming; named
volumes created under generated projects remain operator-owned data.
