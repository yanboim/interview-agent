# 模型策略网关

## 决策

`app/model_gateway.py` 是唯一允许构建 `langchain_openai` 客户端的模块，提供带用途
标签的聊天和Embedding工厂。

每个聊天调用获得：

- 提供方超时和有界重试次数；
- 当SSE尝试在未产生任何chunk前失败时，最多执行配置数量的零chunk流重启；每次重启
  都占用额外的请求模型调用预算，而部分流绝不重放或切换回退模型；
- 同步/异步调用共享的用途级并发Semaphore；
- 输入字符安全预算和输出Token上限；
- 依赖延迟/错误指标；
- 提供方Token用量核算；
- 脱敏 `ModelGatewayError` 映射。

Agent调用还会按用途（`knowledge`、`interviewer`、`evaluator`、`planner`、
`summarization` 或 `schema_repair`）解析模型；未配置覆盖时继承默认模型。
请求级预算记录调用次数、输入/输出Token、墙钟时间、首Token时间、价格版本和估算成本，
并在新增调用会超过请求类别上限前拒绝执行。

启用多Agent执行时，由代码定义的Workflow V2把一个或多个确定性意图映射为有界且有序
的专业Agent集合，不调用规划模型或嵌套编排调用。未知会话输入遵循有界的知识/通用
回答专业Agent策略。已退役的Supervisor拓扑不能通过配置恢复；运维回滚必须加载已记录
并校验摘要的旧版app和worker镜像。对于流式HTTP界面，显式专业Agent并发运行至经过
验证的最终图状态，再由适配器按确定性路由顺序输出每个结构化答案，因为提供方消息流
可能只包含工具证据而没有答案chunk。

可选回退在模型及用途取得获批评测报告前保持关闭，并使用同一提供方端点。Evaluator、
简历分析和面试复盘不会切换到未校准回退模型，而是返回可恢复的不可用状态。

Embedding使用相同的超时、重试、并发、输入预算、指标和安全错误策略。本地Sparse
Embedding和确定性/本地重排不跨提供方网络边界，因此位于网关之外。

输入字符预算是预检安全上限，不是Tokenizer。更精确的会话Token窗口策略由TD-008
单独处理。

## 后果

- 提供方策略只有一个实现点。
- 响应头成功但SSE正文为空并停滞时，可以在不重复可见内容或工具调用chunk的前提下恢复。
- 用途标签区分专业Agent、面试引擎、重排和Embedding遥测。
- Agent图仍负责Prompt/工具编排；网关负责传输可靠性和资源限制。
- `eval/reports/model-routing-canary-approved.json` 记录历史确定性直连路由金丝雀对比，
  不能作为Workflow V2生产证据。
- `scripts.check_workflow_rollout` 保留独立的公开生产观察政策及其历史Supervisor基线。
  已完成的预发布退役改由 `scripts.check_workflow_prerelease` 和不可变回滚产物授权。
