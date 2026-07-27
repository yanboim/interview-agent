# Worktree stack isolation

## Namespace

Compose already prefixes default container, network, and named-volume resources
with its project name. Fixed `container_name` entries bypassed that isolation.
They are removed, and `COMPOSE_PROJECT_NAME` is generated as
`interview-agent-<worktree-name>-<path-hash>`.

## Host ports

The generator assigns one deterministic block per resolved worktree path and
emits explicit values for the app, PostgreSQL, Redis, Qdrant HTTP/gRPC,
Prometheus, Grafana, and Playwright ports. Container-to-container URLs continue
to use service DNS names and fixed internal ports.

Operators can override any emitted value. Generation is atomic and refuses an
unsafe suffix. The local `.env.worktree` contains no credentials.

## Commands

`make worktree-env` creates or refreshes the local environment file.
`make stack-up`, `make stack-config`, and `make stack-down` invoke Compose with
that file. Teardown does not remove volumes unless the operator explicitly runs
Compose with `--volumes`.
