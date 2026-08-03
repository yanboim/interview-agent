# Security model

专题文档：

- [威胁模型](THREAT-MODEL.md)
- [数据分级](DATA-CLASSIFICATION.md)
- [隐私与数据处理](PRIVACY.md)
- [访问控制](ACCESS-CONTROL.md)
- [密钥管理](SECRET-MANAGEMENT.md)
- [安全评审](SECURITY-REVIEW.md)

## Trust boundaries

```text
Browser
  -> public FastAPI routes
     -> authenticated user-owned database records
     -> administrator-only operations
     -> private Qdrant knowledge
     -> configured model, embedding, and optional search providers
```

The browser and all client-supplied identifiers are untrusted. The authenticated
server-resolved identity is authoritative. Infrastructure dependencies and
external providers must be private or explicitly approved for the data sent to
them.

## Authentication and authorization

- Product users register and log in through the product auth endpoints.
- Administrators are created with `python -m scripts.create_admin` and use a
  separate login endpoint and browser session.
- Access and refresh tokens have distinct lifetimes. Refresh rotation and
  logout revoke prior credentials.
- Every user-owned read and write includes the authenticated `user_id`; a
  client-supplied ID does not grant access.
- `/api/admin/*` checks the server-side `admin` role.
- `APP_API_KEY` is a server-only deployment secret for the operator readiness
  probe (`/ready`). Browser APIs never require or expose it; product and admin
  APIs rely on their own Bearer identity, role, ownership, and rate-limit checks.

Executable evidence is indexed by the security features in
[`feature-contract.json`](../product-specs/feature-contract.json), principally
`tests/test_auth.py` and `tests/test_authorization.py`.

## Secrets

- Never commit `.env`, API keys, tokens, credentials, database dumps, or user
  data.
- Use `.env.example` only for names and non-secret placeholders.
- Production secrets can be mounted through `*_FILE` settings for model,
  embedding, web-search, and application API keys.
- Rotate a secret if it appears in logs, documentation, test output, an issue,
  or source history; removing the visible string is not sufficient.
- Keep Grafana defaults, database passwords, token-signing material, and API
  keys distinct across environments.

## Private knowledge and external data flow

Knowledge under `knowledge/` and retrieved Qdrant chunks is private by default.
Do not expose it through public search tools or include it in diagnostics.

- Embedding sends document chunks to the configured embedding provider.
- Chat and interview flows send prompts and selected context to the configured
  model provider.
- LLM reranking sends candidate chunk bodies to that provider and is disabled
  by default.
- Web search sends the query to the configured third-party service and is
  disabled by default.

Planned resume and interview-review features add two proposed flows:

- resume text and the selected job context to the configured model provider;
- explicitly approved interview audio to a separately configured
  transcription provider.

These flows are not implemented. Their target controls are documented in
[用户敏感文件与异步处理](../design-docs/user-sensitive-file-processing.md).

Before enabling a provider, confirm data classification, retention, regional,
and contractual requirements. Evaluation datasets and reports must not contain
unapproved user or private knowledge text.

## Network and deployment controls

- Enable `AUTH_REQUIRED=true`, PostgreSQL, Redis, and a strong `APP_API_KEY` for
  the authenticated production readiness probe.
- Terminate TLS at a trusted ingress and restrict allowed origins and hosts at
  the deployment boundary.
- Keep PostgreSQL, Redis, Qdrant, Prometheus, Grafana, and OpenTelemetry ports on
  private networks.
- Do not expose `/metrics` publicly; protect operational dashboards separately.
- Apply Alembic migrations before accepting traffic.
- Do not weaken authentication, authorization, CSP, audit logging, dependency
  auditing, or image scanning to make a test pass.

## Security-sensitive change checklist

- Identify the actor, resource owner, trust boundary, and denied cases.
- Add cross-user and role-negative tests, not only a successful request.
- Define replay, idempotency, or optimistic-concurrency behavior for retriable
  writes.
- Review logs, metrics, errors, and audit records for secret or private-data
  leakage.
- Map unknown infrastructure and provider exceptions to stable public messages;
  keep the complete exception in restricted server logs only.
- Document every new external data destination, timeout, failure mapping, and
  cost behavior.
- Run focused auth/authorization tests and the full required Harness gate.

Report vulnerabilities through the repository's private maintainer channel. Do
not publish credentials, exploit details, or private user data in a public
issue.
