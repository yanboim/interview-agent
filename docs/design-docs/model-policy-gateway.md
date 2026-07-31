# Model policy gateway

## Decision

`app/model_gateway.py` is the only module allowed to construct
`langchain_openai` clients. It exposes purpose-labelled chat and embedding
factories.

Every chat call receives:

- a provider timeout and bounded retry count;
- a shared purpose-level concurrency semaphore for sync and async calls;
- an input-character safety budget and output-token cap;
- dependency latency/error metrics;
- provider usage token accounting;
- sanitized `ModelGatewayError` mapping.

Agent calls additionally resolve a model by purpose (`supervisor`, `knowledge`,
`interviewer`, `evaluator`, `planner`, `summarization`, or `schema_repair`) and
inherit the default model when no override is configured. A request-scoped
budget records call count, input/output tokens, wall time, first-token time,
price version, and estimated cost, and rejects an additional call before its
configured request-class ceiling is exceeded.

High-confidence single-intent requests may bypass the Supervisor only when the
deterministic classifier and rollout stage both allow it. Ambiguous or
multi-intent requests always retain Supervisor routing. Rollout proceeds
through `off`, `internal`, `canary`, and `production`; setting `off` is the
tested rollback.

Optional fallback remains disabled until the model and purpose have an
approved evaluation report. It uses the same provider endpoint. Evaluator,
resume-analysis, and interview-review calls never cross to an uncalibrated
fallback model and instead return a recoverable unavailable state.

Embeddings use the same timeout, retry, concurrency, input-budget, metric, and
safe-error policy. Local sparse embeddings and deterministic/local rerankers do
not cross a provider network boundary and remain outside this gateway.

The input-character budget is a preflight safety ceiling, not a tokenizer. The
more precise conversation token-window policy is handled separately by TD-008.

## Consequences

- Provider policy changes have one implementation point.
- Purpose labels separate supervisor, specialists, interview engine,
  reranking, and embedding telemetry.
- Agent graphs still own prompt/tool orchestration; the gateway owns transport
  reliability and resource limits.
- `eval/reports/model-routing-canary-approved.json` records the approved
  deterministic canary comparison and rollback evidence; cost-bearing live
  reports remain separately approved artifacts.
