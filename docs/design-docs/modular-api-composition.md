# Modular API composition

## Context

`app/main.py` grew beyond 2,100 lines and owned dependency construction,
middleware, DTO validation, authorization helpers, file operations, model
orchestration, and every HTTP route. This made unrelated changes collide in one
module and allowed route adapters to depend directly on composition globals.

## Decision

Introduce:

```text
app/api/
  runtime.py       one configured dependency container
  schemas.py       transport DTOs
  security.py      identity and role enforcement
  agent_io.py      message/source transport conversion
  routers/
    auth.py
    profile.py
    admin.py
    chat.py
    conversations.py
    interviews.py
    learning.py
```

The composition root constructs concrete adapters and services, configures the
runtime once, installs middleware, and includes each router. Router modules may
depend on API helpers, application services, and domain/infrastructure
interfaces exposed by the runtime; they must not import `app.main`.

Compatibility imports from `app.main` may temporarily expose DTOs and selected
handlers used by existing internal tests or scripts. They are aliases only and
do not restore route ownership to the composition root.

## Consequences

- Dependency construction remains explicit in one place.
- Router tests can replace individual runtime fields without importing hidden
  composition globals.
- The runtime container is process-scoped configuration, not a correctness
  lock or mutable request state.
- Further extraction of model orchestration into application services can
  proceed per domain without editing the composition root.
