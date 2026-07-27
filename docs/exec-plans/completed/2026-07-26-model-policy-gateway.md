# Model policy gateway

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Technical debt: TD-007
- Product contract: `model-policy-gateway`

## Objective

Route all external chat and embedding model construction through one
policy-bearing gateway that enforces timeout, bounded retries, concurrency,
input/output budgets, safe errors, latency/error metrics, and token accounting.

## Non-goals

- Change model providers or prompts.
- Add provider failover.
- Run live cost-bearing evaluations.
- Apply network policy to local deterministic rerankers.

## Acceptance criteria

- Only `app/model_gateway.py` imports `langchain_openai`.
- Single agent, multi-agent specialists/supervisor, interview scoring/question
  generation, LLM reranking, and embeddings use gateway factories.
- Provider timeout and retry limits come from settings.
- Sync and async calls have bounded concurrency.
- Oversized inputs fail before provider I/O; outputs have a hard token cap.
- Provider errors are mapped without leaking provider response bodies.
- Chat calls record latency/error and token metrics exactly once.
- Architecture and policy tests pass, followed by `make harness-check`.

## Progress

- [x] All external model construction and call sites inventoried.
- [x] Chat and embedding gateway implemented.
- [x] All provider adapters migrated.
- [x] Budget, error, concurrency, timeout, retry, and construction tests pass.
- [x] Full Harness and documentation closeout complete.

## Verification

- `pytest -q`: 135 passed, 2 skipped.
- `make harness-check`: architecture/static checks, backend suite, frontend
  unit/type/build/bundle checks, and 10 Playwright scenarios passed.

## Decisions and findings

- Provider SDK construction is mechanically restricted to
  `app/model_gateway.py`.
- Token accounting is owned by the gateway so orchestration layers do not
  double-count usage.
- Embeddings use the same input, concurrency, metric, and safe-error boundary
  as chat models.

## Rollback

This is an adapter policy change with no data migration. Rollback restores
direct provider constructors; prompts and stored data are unchanged.
