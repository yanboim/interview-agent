# 配置管理

## 来源和优先级

运行配置由 `app/config.py` 的Settings定义，从环境变量和 `.env` 读取；支持的Secret
可通过对应 `*_FILE` 挂载。`.env.example`提供无秘密示例。

## 分类

- 模型与Embedding：端点、模型、Key、超时、重试和预算；
- 数据：数据库、Redis、Qdrant集合/别名；
- 检索：候选数、最终数、阈值和重排开关；
- 任务：队列、租约、重试和轮询；
- 安全：认证、Token时长、应用API Key和限流；
- 观测：日志、OTLP、服务名；
- 前端与Worktree：产物路径、Compose project和端口。

## 规则

- 生产必须显式配置安全值，不依赖本地默认密码；
- Secret不进入Git、镜像、日志或生成参考；
- 环境差异记录在 `docs/release/ENVIRONMENTS.md`；
- 新配置提供安全默认、验证、示例、文档和测试；
- 重命名配置需要兼容窗口或明确破坏性发布说明；
- 配置变更与制品版本一起审计。

完整字段参考由 `python -m scripts.generate_docs` 从Settings生成。
