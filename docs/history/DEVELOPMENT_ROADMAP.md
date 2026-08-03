# AI 面试教练后续开发路线图

> 历史状态：本文记录2026-07基础能力建设路线，所列任务已经完成，不再作为当前
> 产品路线图或实现事实来源。当前产品范围见 `docs/product/PRD.md`，当前行为见
> `docs/product-specs/feature-contract.json`。

## 当前进度

- [x] T1：SQLite / PostgreSQL 双兼容存储
- [x] T2：数据库迁移体系
- [x] T3：账号认证与 RBAC
- [x] T4：跨场次能力画像
- [x] T5：面试恢复与历史管理
- [x] T6：学习任务与复习计划
- [x] T7：多工具 Agent
- [x] T8：联网搜索
- [x] T9：RAG 重排与评估扩展
- [x] T10：Redis
- [x] T11：完整可观测性
- [x] T12：CI/CD 与安全
- [x] T13：多 Agent
- [x] T14：管理员后台

## 开发原则

- 先完成数据、身份和可观测性，再增加多 Agent。
- 每个任务必须包含代码、测试、配置、文档和运行验证。
- 新能力保持本地开发可用，同时提供生产环境升级路径。
- 涉及模型调用、联网搜索和知识库外发时必须显式配置和可关闭。

## P0：生产数据与身份底座

### T1：SQLite / PostgreSQL 双兼容存储

范围：

- 使用统一数据库接口保存会话、消息、模拟面试和评分。
- 本地默认使用 SQLite，生产环境通过 `DATABASE_URL` 使用 PostgreSQL。
- 保持现有数据模型和 API 行为兼容。
- 为数据库连接失败增加就绪检查。

验收：

- 现有存储测试全部通过。
- SQLite 持久化和用户隔离回归通过。
- PostgreSQL 容器可以启动并通过 `/ready`。
- 服务切换数据库只需修改环境变量。

### T2：数据库迁移体系

范围：

- 引入 Alembic。
- 建立初始 schema migration。
- 后续表结构变化禁止依赖运行时自动建表。

验收：

- 空数据库可以执行 `alembic upgrade head`。
- 可以检测当前 migration revision。
- Compose 启动流程执行迁移后再启动应用。

### T3：账号认证与 RBAC

状态：已完成（2026-07-24）。

范围：

- 支持注册、登录、退出和访问令牌刷新。
- 密码使用安全哈希，不保存明文。
- 服务端从令牌解析用户身份，不再信任请求体 `user_id`。
- 角色至少包含 `user` 和 `admin`。
- 管理员负责知识库导入和运行状态管理。

实现：

- scrypt 加盐密码哈希，数据库只保存哈希和盐。
- 不透明 access / refresh token，数据库只保存令牌摘要；refresh token
  使用后立即轮换失效。
- `user` / `admin` 两级角色，以及受保护的管理员运行摘要和知识库导入接口。
- 所有会话、消息和模拟面试接口以令牌身份校验 `user_id`。
- PostgreSQL migration `20260724_0002` 创建用户和令牌表。

验收：

- 用户不能读取、删除或继续其他用户的会话与面试。
- 未登录请求受保护接口返回 401。
- 越权请求返回 403。
- 登录、刷新、退出和隔离场景有自动测试。

验证结果：

- 单元及回归测试：41 passed，1 skipped。
- PostgreSQL 集成测试：1 passed。
- 真实 HTTP 验证覆盖 401、403、注册、刷新轮换、退出撤销和用户隔离。

## P1：长期学习闭环

### T4：跨场次能力画像

- 聚合多场面试的主题、维度分数和薄弱点。
- 展示分数趋势、最近训练和高频问题。
- 支持按 Java、Spring、微服务、RAG 等主题筛选。

状态：已完成（2026-07-24）。

实现：

- 基于现有 `interviews` / `interview_turns` 实时聚合，不增加冗余画像表。
- 综合统计训练场次、已答题目、平均分和首尾场次变化。
- 聚合技术准确性、原理深度、表达结构和工程实践四维得分。
- 提供分数趋势、主题表现、薄弱点频次、最近训练和高频问题。
- `GET /api/capability-profile` 支持账号隔离和主题筛选。
- 能力画像页面提供响应式趋势图、进度条和主题交互筛选。

验证结果：

- 单元及回归测试：45 passed，1 skipped。
- PostgreSQL 集成测试覆盖画像源数据查询和用户隔离。
- 空数据、异常历史 JSON、主题筛选和跨场次聚合均有自动测试。

### T5：面试恢复与历史管理

- 列出历史面试。
- 恢复未完成面试。
- 查看每轮问题、回答、评分和反馈。
- 支持归档与删除。

状态：已完成（2026-07-24）。

实现：

- 历史列表展示主题、难度、进度、状态、平均分和更新时间。
- 服务端从持久化题目恢复未完成面试，不依赖浏览器本地状态。
- 详情接口返回每轮问题、回答、评分和反馈。
- 支持归档、取消归档和永久删除，所有操作执行账号隔离校验。
- migration `20260724_0003` 为面试增加归档时间。

### T6：学习任务与复习计划

- 将薄弱点转成可完成的学习任务。
- 记录状态、截止时间和复习次数。
- 根据遗忘周期生成复习安排。
- 完成训练后更新能力画像。

状态：已完成（2026-07-24）。

实现：

- 从能力画像最低维度和高频薄弱点生成去重后的学习任务。
- 任务包含专项行动、待开始/进行中/已完成状态和可修改截止时间。
- 复习打卡记录次数和时间，并按 1、3、7、14、30、60 天间隔安排下次复习。
- 支持任务筛选、更新、复习和删除，且按账号隔离。
- 新面试评分仍实时进入 T4 画像，形成训练—画像—任务—复习闭环。
- migration `20260724_0003` 创建 `learning_tasks` 表和查询索引。

验证结果：

- 单元及回归测试：49 passed，1 skipped。
- PostgreSQL migration 升级至 `20260724_0003 (head)`。
- PostgreSQL 集成测试覆盖学习任务创建、复习调度和清理。

## P2：工具与检索能力

### T7：多工具 Agent

- 将出题、评分、保存薄弱点、查询进度和学习计划封装为工具。
- 保留当前知识库工具。
- 为每个工具增加输入模型、权限和审计日志。

状态：已完成（2026-07-24）。

- Agent 工具包含私人知识检索、学习进度查询和个人学习计划生成。
- 通过请求级上下文向工具传递服务端认证身份，不信任模型提供的用户 ID。
- 工具调用记录用户、角色、工具名、状态、耗时和截断摘要。
- 管理员可通过 `/api/admin/tool-audits` 检索审计记录。

### T8：联网搜索

- 支持显式启停。
- 只在私人知识库不足时使用。
- 返回来源链接、抓取时间和引用。
- 对外发查询和第三方内容增加安全边界。

状态：已完成（2026-07-24）。

- `WEB_SEARCH_ENABLED` 默认关闭，只有显式配置后才向 Agent 注册联网工具。
- 支持 Tavily 兼容搜索接口，结果包含标题、URL、抓取时间和摘要。
- 系统提示禁止把私人知识块或个人信息加入外发查询。
- 外发前限制长度并拦截疑似 API Key、Bearer Token 和长十六进制密钥。
- 未配置 Key、无结果或服务异常时返回明确状态，不伪造网络来源。

### T9：RAG 重排与评估扩展

- 在明确允许知识块外发后评估 GLM 列表式重排。
- 扩大人工标注的 chunk 级数据集。
- 增加 Recall@K、nDCG、引用准确性和答案忠实度。
- 建立每次导入后的回归评估。

状态：已完成（2026-07-24）。

- 保留 Cross-Encoder、GLM 列表式和轻量词法三种可切换重排路径。
- chunk 级评估新增 nDCG@K，并保留 Top-1、Recall/Hit@K 和 MRR。
- 答案级评估新增引用精确率、引用召回率和人工标注 claim 忠实度。
- `INGEST_RUN_EVALUATION=true` 时导入后自动生成
  `post-ingest-latest.json`，并可用 `RAG_REGRESSION_MIN_NDCG` 设置门禁。
- 回归与联网搜索均默认关闭外部调用，避免未经确认的知识库外发和模型成本。

验证结果：

- 自动化测试：56 passed，1 skipped。
- 答案评估集：引用精确率 0.833、召回率 1.0、忠实度 0.889。

## P3：生产运行体系

### T10：Redis

状态：已完成（2026-07-24）。

- 多实例共享限流。
- 缓存高频检索和短期状态。
- 为后台任务提供队列基础。

实现：Redis 固定窗口共享限流、RAG 查询结果 TTL 缓存、知识库导入任务队列和
独立 Worker；Redis 不可用时限流自动退回单实例内存模式。

### T11：可观测性

状态：已完成（2026-07-24）。

- 结构化日志和关联 ID。
- OpenTelemetry Trace。
- Prometheus + Grafana 仪表盘。
- GLM、Embedding、Qdrant 和数据库延迟与错误率告警。

实现：JSON 日志与 `X-Request-ID`、FastAPI/SQLAlchemy OpenTelemetry Trace、
依赖调用计数/耗时/错误 Prometheus 指标、预置 Grafana 面板和依赖错误/慢调用
告警。Embedding 与 Qdrant 检索以 `embedding_qdrant` 端到端指标记录。

### T12：CI/CD 与安全

状态：已完成（2026-07-24）。

- 自动测试、镜像构建和依赖漏洞扫描。
- 数据库 migration 检查。
- 容器非 root、安全头、密钥管理和备份恢复演练。

实现：GitHub Actions 执行测试、migration、pip-audit、镜像构建和 Trivy；
Dependabot 跟踪依赖更新；应用容器使用非 root 用户、移除 Linux capabilities
并启用安全响应头；支持 Docker secret 文件；PostgreSQL 与 Qdrant 已完成真实
备份和非破坏性恢复校验。

验证结果：

- 自动化测试：60 passed，1 skipped。
- Compose 全栈：应用、PostgreSQL、Qdrant、Redis、Worker、OpenTelemetry、
  Prometheus、Grafana 均已启动。
- `/health`、`/ready`、Prometheus target、Grafana 预置仪表盘和告警规则通过。
- 备份演练：`backups/20260724T173712Z`，PostgreSQL dump 与 Qdrant snapshot
  manifest 校验通过；未执行破坏性的实际恢复。

## P4：可选架构升级

### T13：多 Agent

状态：已完成（2026-07-24）。

- Supervisor 负责任务路由。
- Knowledge Agent 负责知识检索。
- Interviewer Agent 负责问题和追问。
- Evaluator Agent 负责评分。
- Planner Agent 负责长期学习计划。

实现：

- `interview_supervisor` 只负责意图识别、专业 Agent 委派和最终答案整合。
- Knowledge Agent 独占私人 RAG 与可选公开网络检索工具。
- Interviewer Agent 负责聊天中的出题/追问，并接管模拟面试出题指标。
- Evaluator Agent 负责回答评价，并接管模拟面试四维评分指标。
- Planner Agent 先读取跨场次画像，再按用户明确意图生成长期学习任务。
- `MULTI_AGENT_ENABLED=false` 可无迁移回退到原单 Agent。
- Prometheus 按 Agent 记录调用、错误、耗时和输入/输出 Token，Grafana 增加
  Token 趋势面板。

进入条件：

- 单 Agent 工具调用和成本指标稳定。
- 跨场次画像与学习计划已经形成闭环。
- 有足够评估集证明多 Agent 带来可量化收益。

验证结果：

- 自动化测试：67 passed，1 skipped。
- 真实 GLM-5.2 首跳路由评估：16/16，准确率 100%。
- Knowledge、Interviewer、Evaluator、Planner 各 4 条，分别达到 100%。
- 评估集：`eval/agent_routing.jsonl`；报告：
  `eval/reports/multi-agent-routing.json`。

## P5：管理员后台

### T14：可视化管理控制台

状态：已完成（2026-07-24）。

- 独立 `/admin` 管理入口，仅允许 `admin` 角色访问数据。
- 运行概览展示业务计数、PostgreSQL、Qdrant、Redis、功能开关和 Agent 拓扑。
- 知识库支持 `.md` / `.txt` 文件上传、列表、删除和 Redis 后台导入进度。
- 知识文件使用 Compose `knowledge_data` 卷持久化，并由应用和 Worker 共享。
- 用户管理支持用户列表、训练数据计数和 `user` / `admin` 角色调整。
- 保护当前管理员和系统最后一个管理员，避免误操作导致后台失去管理权限。
- 工具审计展示调用用户、工具、状态、耗时和输入摘要。
- 前台管理员账号登录后显示“后台”快捷入口。

验证结果：

- 自动化测试：71 passed，1 skipped。
- 管理页面 JavaScript 语法、知识文件安全校验、角色更新和任务状态通过测试。
