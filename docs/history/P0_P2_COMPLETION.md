# P0–P2 完成与验收矩阵

> 历史状态：本文是2026-07-25版本的发布验收记录。后续实现已继续演进；当前行为、
> 架构和验证分别以功能契约、`ARCHITECTURE.md` 和自动化测试为准。

更新时间：2026-07-25

本文记录本轮产品体验 P0–P2 的实现位置、验证方式和生产切换条件。
它补充 `DEVELOPMENT_ROADMAP.md` 中已有的基础设施 P0–P2。

## P0：核心体验闭环

| 需求 | 实现证据 | 验收证据 |
| --- | --- | --- |
| 目标岗位与 JD 按账号保存 | `user_profiles`、`GET/PUT /api/profile` | SQLite 存储测试、PostgreSQL 0005 迁移 |
| 聊天引用随历史保存 | `messages.metadata_json`、结构化 `sources` | 历史元数据测试、Markdown 组件测试 |
| 同题重答、参考答案和分数对比 | `interview_answer_attempts`、retry API | 首答/重答历史测试 |
| 核心产品事件 | `product_events`、客户端 `trackEvent` | 用户隔离测试、后台产品分析页 |
| PostgreSQL 兼容 | Alembic 0001–0007 | 隔离 PostgreSQL 全迁移和集成测试通过 |

## P1：长期训练产品

| 需求 | 实现证据 | 验收证据 |
| --- | --- | --- |
| 账号安全 | 登录态改密；一次性恢复码找回密码；操作后撤销全部令牌 | 改密、恢复码轮换与会话撤销测试 |
| 每日提醒 | 账号级时区/时间偏好、到期任务 API、浏览器通知 | 存储测试与前端类型检查 |
| 动态推荐 | `/api/today-plan` 综合目标、JD、进行中面试、到期任务和薄弱点 | 今日训练页真实浏览器验证 |
| 岗位准备度 | 能力画像增加准备度、置信度和前三优先项 | 前端生产构建与 E2E |
| 富来源 | 私有来源摘要；公开来源标题、URL、抓取时间、摘要 | 历史持久化与流式事件测试 |
| 会话管理 | 日期分组、搜索、重命名、批量归档/恢复、删除 | 存储隔离测试与移动端 E2E |
| 产品细节 | favicon、状态反馈、触控和键盘焦点 | axe、桌面与移动端 E2E |

## P1：前端架构

- 功能面板通过 `defineAsyncComponent` 独立分包；`AppView` 约 17 KB，
  Markdown 运行时独立分包。
- 原 2600 行主样式拆为 sidebar、chat、interview、profile、
  learning/responsive 五个领域文件。
- 新增 `UiButton`、`UiState` 基础组件。
- 目标、会话、消息、面试进行态、学习任务均以服务端账号数据为权威；
  浏览器存储只保留令牌、主题和短期消息缓存等设备偏好。

## P2：质量、观测和发布

- Vitest 覆盖流式协议、Markdown 净化、表格渲染和共享组件状态。
- Playwright 覆盖 Desktop Chrome 与 Pixel 7；验证无横向溢出和键盘焦点。
- axe 阻断 critical/serious 问题；本轮据此修复浅色主题文字对比度。
- Bundle 门禁限制 AppView、Markdown runtime 和应用 CSS 体积。
- 客户端捕获 `error`、`unhandledrejection`、页面加载与 LCP，并写入产品事件。
- 管理后台提供核心漏斗、活跃用户、客户端错误与事件分布。
- CI 执行类型检查、单元/组件测试、E2E、npm/pip 审计、镜像与 Trivy 扫描。
- release workflow 支持 canary/production GitHub Environment 审批、镜像归档和校验和。

## 当前验证结果

- Python：80 passed，包含真实 PostgreSQL 集成测试。
- Frontend：8 passed。
- Playwright：4 passed（桌面与移动）。
- TypeScript、生产构建、Bundle budgets：通过。
- npm audit：0 vulnerabilities。
- PostgreSQL 隔离测试库：从空库升级至 `20260725_0007` 并通过读写回归。

## 生产切换

2026-07-25 已获得生产部署授权并完成切换：

- 迁移前 PostgreSQL 备份：
  `backups/20260725T174400Z-pre-p0p2.dump`；
  SHA-256：
  `f89396a90c07df4c7297e47530ff86fd7970110e0af1fb3204d877e5cc11aebc`。
- app/worker 已切换至本轮构建镜像；app 启动时顺序执行
  `0004 → 0005 → 0006 → 0007`。
- 生产数据库 revision 为 `20260725_0007`；部署前后核心数据计数一致：
  users 3、conversations 5、messages 10、interview_turns 8。
- app 为 healthy，worker 正常运行；`/health` 返回 `ok`，
  `/ready` 返回 `ready`。
- 桌面 Chrome 与 Pixel 7 生产冒烟通过：页面非空、无错误覆盖层、
  无横向溢出、登录入口与 favicon 正常、无非预期控制台/页面/网络错误。

0005/0006/0007 仅新增列、表和索引。备份继续保留，若后续回滚，应先评估迁移后新增数据，
不要在保留新数据的情况下盲目执行 downgrade。
