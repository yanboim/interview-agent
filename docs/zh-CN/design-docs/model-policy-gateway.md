# 模型策略网关

## 决策

`app/model_gateway.py` 是唯一允许构建 `langchain_openai` 客户端的模块，提供带用途
标签的聊天和Embedding工厂。

每个聊天调用获得：

- 提供方超时和有界重试次数；
- 同步/异步调用共享的用途级并发Semaphore；
- 输入字符安全预算和输出Token上限；
- 依赖延迟/错误指标；
- 提供方Token用量核算；
- 脱敏 `ModelGatewayError` 映射。

Agent调用还会按用途（`supervisor`、`knowledge`、`interviewer`、`evaluator`、
`planner`、`summarization` 或 `schema_repair`）解析模型；未配置覆盖时继承默认模型。
请求级预算记录调用次数、输入/输出Token、墙钟时间、首Token时间、价格版本和估算成本，
并在新增调用会超过请求类别上限前拒绝执行。

只有确定性分类器给出高置信单意图且发布阶段允许时，请求才能跳过Supervisor。模糊或
多意图请求始终保留Supervisor路由。发布依次经过 `off`、`internal`、`canary` 和
`production`；切换到 `off` 是经过测试的回滚方式。

可选回退在模型及用途取得获批评测报告前保持关闭，并使用同一提供方端点。Evaluator、
简历分析和面试复盘不会切换到未校准回退模型，而是返回可恢复的不可用状态。

Embedding使用相同的超时、重试、并发、输入预算、指标和安全错误策略。本地Sparse
Embedding和确定性/本地重排不跨提供方网络边界，因此位于网关之外。

输入字符预算是预检安全上限，不是Tokenizer。更精确的会话Token窗口策略由TD-008
单独处理。

## 后果

- 提供方策略只有一个实现点。
- 用途标签区分Supervisor、专业Agent、面试引擎、重排和Embedding遥测。
- Agent图仍负责Prompt/工具编排；网关负责传输可靠性和资源限制。
- `eval/reports/model-routing-canary-approved.json` 记录获批的确定性金丝雀对比和回滚
  证据；产生费用的Live报告仍作为单独审批的产物保存。
