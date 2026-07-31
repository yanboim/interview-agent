# Agent与模型架构

## 目标

Agent负责把用户意图路由到知识、面试、评估和学习计划能力。它不拥有认证、授权、
业务提交或数据库事务决定。

## 结构

```text
API / application service
  -> request-scoped authenticated context
  -> supervisor
      ├── knowledge specialist
      ├── interviewer specialist
      ├── evaluator specialist
      └── planner specialist
  -> tools
      ├── private knowledge retrieval
      ├── optional public search
      ├── learning progress
      └── learning plan
  -> model policy gateway
  -> configured provider
```

当 `MULTI_AGENT_ENABLED=false` 时，面试能力可退回单Agent路径，但身份、模型策略和
工具审计要求不变。

## 安全边界

- 工具从请求级上下文取得服务端身份，不接受模型自由声明的用户身份；
- 公开搜索默认关闭，并在网络调用前阻止凭据、高熵Token、个人信息、简历或逐字稿
  片段作为查询；带有私人上下文线索或过长的模糊查询只生成预览，当前用户在后续消息
  明确确认后才原子领取并执行一次，重复确认只重放已存结果；
- 工具输入使用结构化模型并在服务端授权；
- 私人知识和公开网页结果均标记为不可信证据，其正文不能覆盖系统指令或触发工具；
- 工具审计只记录名称、状态、耗时、输入哈希/长度和安全错误类别，不复制查询、
  Prompt、检索正文或工具结果；
- Agent变更学习任务前先生成预览，只有当前用户明确确认所有者绑定、内容绑定且未过期
  的预览后才可应用；重复确认重放原结果；
- 模型输出不能直接执行文件、数据库或管理员操作。

## 模型策略

`app/model_gateway.py` 是外部Chat和Embedding客户端构造入口，统一应用：

- 超时和有限重试；
- 最大并发；
- 输入字符和输出Token预算；
- 安全错误映射；
- 延迟、错误和Token指标。

Prompt和结构化输出模式由业务适配器拥有；Gateway不决定业务提示词。

## 上下文

消息表是历史事实来源。`chat_context.py`从持久摘要、最近完成消息和当前请求构造
受预算约束的派生窗口。摘要游标与聊天领取事务一起推进，避免失败重试重复压缩。

## 质量

- 委派、专业Agent结果、评分、训练预览和逐条引用使用 `agent_contracts.py` 中的
  版本化Pydantic契约；提供方支持时使用原生结构化输出，否则只允许一次有限修复；
- 私人知识分块与公开URL具有稳定证据ID。回答用这些ID标注重要事实，并通过版本化
  `citations` 流事件区分有证据、无证据和证据冲突；旧的turn级 `sources` 事件继续保留；
- 生成产物和执行轨迹持久化Prompt、Schema与模型版本，历史消息重放同一引用元数据；
- Supervisor路由由版本化数据集报告总体和分Agent准确率；
- 模型评分解析会归一化维度结构；
- 检索和回答质量使用独立评估集；
- 更换模型、Prompt、工具或路由策略必须运行对应回归，而不能只依赖人工对话。
