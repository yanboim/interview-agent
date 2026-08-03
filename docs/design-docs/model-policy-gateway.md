# Model policy gateway

## Decision

`app/model_gateway.py` is the only module allowed to construct
`langchain_openai` clients. It exposes purpose-labelled chat and embedding
factories.

Every chat call receives:

- a provider timeout and bounded retry count;
- at most the configured zero-chunk stream restarts when an SSE attempt fails
  before yielding anything; every restart consumes another request model-call
  budget, while a partial stream is never replayed or switched to fallback;
- a shared purpose-level concurrency semaphore for sync and async calls;
- an input-character safety budget and output-token cap;
- dependency latency/error metrics;
- provider usage token accounting;
- sanitized `ModelGatewayError` mapping.

Agent calls additionally resolve a model by purpose (`knowledge`, `interviewer`,
`evaluator`, `planner`, `summarization`, or `schema_repair`) and
inherit the default model when no override is configured. A request-scoped
budget records call count, input/output tokens, wall time, first-token time,
price version, and estimated cost, and rejects an additional call before its
configured request-class ceiling is exceeded.

When multi-agent execution is enabled, the code-defined Workflow V2 maps one or more
deterministic intents to a bounded ordered set of specialists without a
planning-model or nested orchestration call. Unknown conversational input follows
the bounded knowledge/general-response specialist policy. The retired Supervisor
topology cannot be restored by configuration; operational rollback loads the
recorded, digest-verified previous app and worker images. For the streaming HTTP
surface, explicit specialists run concurrently to their validated final graph
state; the adapter then emits each structured answer in deterministic route order,
because a provider message stream may contain tool evidence without answer chunks.

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
- A response-header success followed by an empty stalled SSE body is
  recoverable without duplicating visible content or tool-call chunks.
- Purpose labels separate specialists, interview engine,
  reranking, and embedding telemetry.
- Agent graphs still own prompt/tool orchestration; the gateway owns transport
  reliability and resource limits.
- `eval/reports/model-routing-canary-approved.json` records the historical
  deterministic direct-routing canary comparison. It is not Workflow V2
  production evidence.
- `scripts.check_workflow_rollout` retains the separate public-production
  observation policy and its historical Supervisor baseline. The completed
  pre-release retirement is instead authorized by
  `scripts.check_workflow_prerelease` and immutable rollback artifacts.
