# 为新接手工程师编写一份独立的「循序渐进 + 速查参考 + cookbook」混合式完整手册

## 背景与定位（先讲清"为什么是独立新文件"）

项目里已有一份 `docs/ENGINEERING-HANDOVER-MANUAL.md`（625 行，精炼速查式：先记10件事 + 14节概览 + 命令速查）。用户明确要求"另写一份独立手册"。为避免重复造轮子、维护漂移，新手册**定位为现有手册的互补**：

| 维度 | 现有 `ENGINEERING-HANDOVER-MANUAL.md` | 新手册 `ONBOARDING-GUIDE.md` |
|---|---|---|
| 形态 | 精炼速查 / 熟手查阅 | 循序渐进教程 + 详尽参考附录 + 任务 cookbook |
| 主线 | 平铺的功能区（14节） | 时间线（Day1 → 独立值守）+ 分类速查 |
| 深度 | 点到为止、指向子文档 | 完整参考表（API/表/环境变量全集）+ 手把手步骤 |

两者会在各自开头互相引用、说明分工。

## 文件位置与登记

- **新建** `docs/ONBOARDING-GUIDE.md`（中文，主文件）
- **修改** `docs/README.md`：在"按角色进入"表的"新接手工程师"行下补充新手册入口，并标注分工（速查 → ENGINEERING-HANDOVER-MANUAL；完整教程 → ONBOARDING-GUIDE）
- **新建** `docs/exec-plans/active/2026-07-29-onboarding-guide.md`：遵循 exec-plans/README.md 模板记录本次工作（目标/非目标/验收标准/实施步骤/进度/决策/回滚），符合仓库"非trivial工作要有执行计划"的要求

> 不修改任何 `docs/generated/` 内容（那是脚本生成的，禁手改）。新手册引用 API/配置/数据字典时**链接到 generated 文档**而非内联复制，避免随代码漂移。

## 手册内容大纲（`ONBOARDING-GUIDE.md`）

### 开篇
- 标题《Interview Agent 新工程师完整上手指南》
- 一段"本文与现有手册的关系"：明确分工、避免读者困惑
- "事实来源优先级"声明（测试/DB → feature-contract → 架构文档 → 运维/README → 历史报告）

### 上篇 · 循序渐进上手（教程主线）
- **第1章 认识这个系统**：它是什么（AI面试教练/求职者训练工作台，非招聘决策系统）、技术栈一览表（FastAPI/Vue/PostgreSQL/Redis/Qdrant/GLM）、系统全景图（复用并扩充现有手册的 ASCII 图）、组件职责表
- **第2章 Day 1：把项目跑起来**
  - 2.1 前置条件与版本核对（Python 3.12 / Node 20.19 / Docker）+ 预期输出
  - 2.2 依赖安装（venv + 带哈希 pip install + npm ci + cp .env）逐步命令
  - 2.3 两条启动路径：Worktree 隔离 Compose 栈（推荐）vs 前后端分开开发；各自预期输出与验证（/health /ready）
  - 2.4 动手任务：浏览器走通 注册→设目标→聊天→面试→能力画像，对照 `/docs` OpenAPI
- **第3章 Day 2-3：读懂一次请求的旅程**
  - 3.1 分层依赖（API adapter → application service → domain ← infrastructure）+ 架构测试如何强制
  - 3.2 追踪一次聊天请求：路由 → ChatTurnService 幂等/认领 → chat_context 规划预算 → RAG/Agent → model_gateway → 流式落库（标注每个文件路径）
  - 3.3 追踪一次模拟面试答题：幂等键、claim token、四维评分、状态机
  - 3.4 动手任务：在 application 层加一个最小改动并跑聚焦测试
- **第4章 第一周：独立完成一个小闭环**——选题原则（无Schema/外部流变化）、改对层、跑 `make harness-check`、同步契约文档、跟随一次非生产知识发布/Worker任务

### 中篇 · 使用手册
- **第5章 普通用户使用**：登录/目标/今日训练/聊天/面试/能力/学习/设置；简历闭环（默认关）；复盘闭环（默认关，音频需三重条件）
- **第6章 管理员使用**：独立 /admin 登录面、create_admin 命令、后台五大能力、读取跨用户内容也被审计
- **第7章 API 调用方**：认证机制（Bearer）、APP_API_KEY 的定位、流式 NDJSON 协议要点、链接到 generated/api-routes.md（不内联复制完整表）、curl 示例（登录→拿token→发一次chat）

### 下篇 · 运维与发布
- **第8章 日常运维**：每班检查清单（命令+检查项）、health vs ready 区别、日志/指标/Trace 三件套、Worker 四类任务与排障、备份校验与受控恢复、知识库发布与回滚
- **第9章 发布与回滚**：四个回滚面（应用/Schema/配置/知识）、最短发布清单、record_release、Secret泄露处理
- **第10章 故障速查表**：复用并扩充现有手册的故障表，补充"先检查/不要做"

### 附录 · 速查参考（手册核心增量价值，现有手册未展开）
- **附录A 目录导航树**：app/ 与 frontend/src/ 的带注释树状图，每个目录一行职责说明
- **附录B 环境变量分组速查**：按 模型/Embedding/DB/Redis-Qdrant/认证/检索重排/搜索/简历/复盘/观测/Secret文件 分组的关键变量表（默认值 + 作用 + 本地建议 + 生产要求）
- **附录C 关键数据表速查**：users/conversations/chat_turns/interviews/interview_turns/learning_tasks/resume_*/interview_review*/audit_events/execution_traces 等核心表的职责一句话说明（不复制完整schema，指向 app/database.py）
- **附录D 常见任务 cookbook**（场景驱动）：
  - 开发：我要新增一个API端点 / 我要改数据库表 / 我要接入新的模型调用 / 我要加一个前端页面
  - 运维：我要发布新版本 / Worker任务卡住怎么排查 / 我要备份和恢复 / 我要回滚知识库
  - 使用：新用户快速上手 / 管理员日常操作
- **附录E 命令速查**：环境启动/本地开发/数据库/验证/运行/受控管理/停止 全集
- **附录F 进阶学习路线**：独立值守前能力清单 + 关键设计文档阅读顺序

## 编写原则（确保不漂移、不重复）

1. **不复制 generated 内容**：API 路由全集链接 `generated/api-routes.md`、配置全集链接 `generated/configuration.md`、数据字典链接 `generated/data-dictionary.md`，避免随代码漂移
2. **命令与文件路径以实际代码为准**：已交叉核对 Makefile / Dockerfile / docker-compose.yml / app/main.py / scripts/
3. **与现有手册分工明确**：现有手册偏速查，新手册偏教程与参考附录；两者互相引用
4. **遵循仓库事实来源优先级**，在手册开头声明

## 验证与完成标准

- 新手册内容与实际代码/命令一致（不引入错误步骤）
- `docs/README.md` 登记，读者可发现新手册
- 执行计划文件符合 exec-plans 模板
- 运行 `make harness-static` 确认未破坏文档/契约校验（这是唯一可跑的只读门禁，不涉及外部服务）

## 不做的事（非目标）

- 不修改任何 `docs/generated/` 或 `docs/zh-CN/` 内容
- 不改任何代码、迁移、配置
- 不运行 Live 模型/RAG 评估（成本操作）
- 不删除或覆盖现有 `ENGINEERING-HANDOVER-MANUAL.md`