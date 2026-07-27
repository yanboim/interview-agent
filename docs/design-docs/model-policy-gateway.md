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
