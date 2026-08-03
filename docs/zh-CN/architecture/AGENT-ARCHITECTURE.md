# Agent与模型架构

## 目标

Agent负责把用户意图路由到知识、面试、评估和学习计划能力。它不拥有认证、授权、
业务提交或数据库事务决定。

## 结构

```text
API / application service
  -> request-scoped authenticated context
  -> code-defined guard / context / route plan
      |-- multi-agent enabled: explicit bounded Workflow V2
      ├── knowledge specialist
      ├── interviewer specialist
      ├── evaluator specialist
      └── planner specialist
      `-- multi-agent disabled: independent single agent
  -> tools
      ├── private knowledge retrieval
      ├── optional public search
      ├── learning progress
      └── learning plan
  -> model policy gateway
  -> configured provider
```

显式工作流按代码生成已知执行顺序，不为普通请求增加规划模型调用。单意图只执行一个
专家，多意图并发执行相互独立的最多四个专家，并以确定顺序验证、组合和持久化。
`MULTI_AGENT_ENABLED=false` 时使用独立单Agent路径；已退休的rollout变量不会恢复旧
拓扑。两条路径的身份、预算、模型策略、确认协议和工具审计要求不变。

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

`AgentContextService`为每个回合构建一次不可变快照，只包含服务端身份、资料/JD、
已确认记忆、能力薄弱点、到期任务和有界会话视图。专业Agent收到一个版本化
`DelegationEnvelope`，包含目标、请求、必要先前回合、约束、期望Schema和关联ID，
而不是完整复制聊天历史。

## 持久工作流

个性化训练计划使用应用拥有的 `agent_runs` 和 `agent_steps`。计划先生成预览，用户
确认后才执行创建学习任务的命令步骤。稳定幂等键、输入摘要、所有者围栏和存储结果
支持并发确认、网络重试、取消及过期领取恢复。LangGraph只负责进程内编排，不是业务
状态事实来源；SSE只输出生命周期事件，不输出隐藏推理。

## 质量

- 委派、专业Agent结果、评分、训练预览和逐条引用使用 `agent_contracts.py` 中的
  版本化Pydantic契约；提供方支持时使用原生结构化输出，否则只允许一次有限修复；
- 私人知识分块与公开URL具有稳定证据ID。回答用这些ID标注重要事实，并通过版本化
  `citations` 流事件区分有证据、无证据和证据冲突；旧的turn级 `sources` 事件继续保留；
- 生成产物和执行轨迹持久化Prompt、Schema与模型版本，历史消息重放同一引用元数据；
- 显式路由由版本化数据集报告总体和分Agent准确率；
- 退休证据由已批准的预发布报告固定：230项确定性评测、6项真实模型验收、四专家、
  两项多意图、精确清理、不可变当前/回滚制品和项目所有者后验批准；
- 历史Supervisor生产查询和双窗口门禁只用于审计公开发布前已经形成的证据，不是当前
  镜像中的运行路径；
- 模型评分解析会归一化维度结构；
- 检索和回答质量使用独立评估集；
- 更换模型、Prompt、工具或路由策略必须运行对应回归，而不能只依赖人工对话。

版本化Agent质量套件至少包含100个路由、50个证据回答、30个多轮委派、30个安全和
20个确认/工作流案例。隐私、越权变更、伪造来源和跨用户失败零容忍。用户回合反馈先
以内容最小化候选进入评估闭环，只有完成隐私评审才能加入脱敏语料。

## 成本与弹性

`model_routing.py` 按知识、面试官、评估、规划、摘要和Schema修复解析模型。多Agent
开启时，一个或多个确定性意图总是进入显式工作流。每个请求限制调用数、输入/输出
Token和估算成本，并记录首Token时间。
同提供方回退必须有评估批准；评估、简历分析和面试复盘不得切换到未校准模型。
