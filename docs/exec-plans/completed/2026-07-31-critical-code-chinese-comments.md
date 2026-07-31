# Critical-code Chinese comments

- Status: completed
- Date: 2026-07-31
- Owner: repository maintainers
- Technical debt: none
- Product contract: no behavior change
- Next action: none.

## Objective

在不改变运行行为的前提下，为项目关键业务与基础设施代码补充必要的中文注释，
帮助中文开发者理解模块职责、事务/并发边界、安全约束和降级策略。

## Non-goals

- 不逐行翻译代码、类型名或显而易见的控制流。
- 不借注释任务重构实现、改变 API、数据库结构或产品行为。
- 不手工修改自动生成的 `docs/generated/` 或 `docs/zh-CN/` 内容。
- 不运行会访问真实模型、Qdrant 或其他付费外部服务的评估。

## Acceptance criteria

- 后端主要运行链路均有中文模块说明：API/应用服务、存储、模型与 Agent、RAG、
  知识发布、后台任务和用户文件。
- 非显然的幂等领取、owner fencing、事务范围、上下文裁剪和安全降级有就近注释。
- 前端复杂异步状态与请求防串写约束有必要中文说明。
- 注释不声称尚未实现的行为，且不改变可执行代码。
- `make docs-generate`、针对性语法/静态检查和 `make harness-check` 通过。

## Affected contracts and architecture rules

产品契约不变。注释必须与 `ARCHITECTURE.md` 中的依赖方向一致，尤其是：外部模型
统一经过网关、同步数据库工作经过共享执行器、用户数据由服务端身份限定、知识发布
先验证候选再切换别名，以及可重试写入依赖数据库幂等/并发条件。

## Implementation steps

1. 盘点 Python、TypeScript 和 Vue 源文件及现有注释分布。
2. 阅读关键模块的公开入口、长函数和状态转换，确定需要解释的设计意图。
3. 分批添加模块说明与少量关键内联注释，保持实现零改动。
4. 生成文档镜像，运行语法、静态架构、前端和完整 Harness 检查。
5. 复核差异与注释准确性，记录证据并将计划移入 `completed/`。

## Progress

- [x] 已阅读架构、产品契约、执行计划规范和技术债追踪器。
- [x] 已盘点约 2.5 万行运行代码与现有中文注释分布。
- [x] 已为后端 API、应用服务、领域计算、存储、模型/Agent、RAG、知识发布、
      Worker 和运维脚本补充中文模块说明与关键约束注释。
- [x] 已为前端聊天、模拟面试、简历和复盘 Store 补充异步防串写、幂等键与
      revision 乐观并发说明。
- [x] `python3 -m compileall -q app scripts migrations` 通过。
- [x] `npm run type-check --prefix frontend` 通过。
- [x] 关键后端测试通过：60 passed。
- [x] `make docs-generate` 完成，中文镜像保持同步。
- [x] `make harness-check` 通过：静态门禁 17 passed；后端 231 passed、
      2 skipped；前端单元测试 18 passed；浏览器 E2E 24 passed。

## Decisions and unexpected findings

- 仓库工作目录中的 `.git` 是受限的空挂载，普通 Git 命令无法读取基线；修改时将
  使用显式文件清单和补丁记录保护现有内容，并在交付说明中如实报告该限制。
- 注释覆盖以关键正确性边界为单位，不以“每个函数都有注释”为目标；机械注释会
  掩盖真正重要的约束，并增加未来维护漂移。
- 本次只新增或翻译注释及执行计划记录，没有修改可执行表达式、API、schema 或
  产品契约。完整 Harness 的通过进一步验证了行为未漂移。

## Rollback / migration considerations

仅注释和执行计划文档变更，无数据库迁移与运行时回滚要求；可按文件撤销新增注释。
