# 应用组件架构

## 依赖方向

```text
app/main.py (composition root)
  -> app/api/routers + schemas + security
      -> app/application services
          -> domain policy/calculations
          -> storage/model/retrieval interfaces and adapters
```

依赖只向业务核心方向流动，任何应用模块不得反向导入组合根。

## API层

- `app/main.py`：构建设置、Store、执行器、Agent、Redis、指标和路由依赖；
- `app/api/runtime.py`：共享运行时依赖结构；
- `app/api/security.py`：请求身份和角色约束；
- `app/api/schemas.py`：HTTP DTO；
- `app/api/routers/`：认证、聊天、会话、面试、简历、真实面试复盘、画像/学习、
  资料和管理适配器；
- `app/api/execution.py`：同步用例进入共享线程边界。

API层拥有HTTP校验、状态码和序列化，不拥有业务事务、Prompt或模型重试。

## 应用服务层

- `chat_service.py`：聊天上下文、回合领取、模型调用、完成/失败/取消；
- `interview_service.py`：面试答案幂等领取、评分、下一题和条件完成；
- `resume_service.py`：文件解析、分析任务、事实约束稿、乐观编辑和DOCX导出；
- `interview_review_service.py`：转写、逐字稿版本确认、问答配对和复盘提交；
- 应用服务协调外部调用与短数据库事务，但不持有跨模型调用的数据库事务。

## 领域与策略

- `learning.py`：学习任务候选和复习间隔；
- `capability.py`：能力聚合；
- `chunks.py`、`chunking.py`：稳定分块身份和标题上下文；
- `evaluation.py`：检索和回答质量指标；
- `chat_context.py`：上下文预算、摘要和窗口计划。
- `resume_engine.py`、`resume_interview.py`：确定性解析结果校验、事实约束和简历出题
  上下文；
- `interview_review_engine.py`：逐字稿片段、问答配对和结构化复盘校验。

纯计算模块不依赖FastAPI、数据库、Redis、Qdrant或模型SDK。

## 基础设施适配器

- `storage.py`、`database.py`：同步SQLAlchemy Core；
- `model_gateway.py`：模型/Embedding策略入口；
- `rag.py`、重排器：检索；
- `operations.py`：Redis、限流、任务和指标；
- `knowledge_publication.py`：版本解析、别名切换和发布锁；
- `user_files.py`、`transcription.py`：服务端文件键和可配置转写适配器；
- `request_audit.py`、`system_resources.py`：安全请求审计与管理员运行状态读取模型；
- `telemetry.py`、`logging_config.py`：观测。

架构约束由 `tests/test_architecture.py` 执行验证。
