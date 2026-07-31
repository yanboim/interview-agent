# 简历中心页面 UI 优化

- 状态：completed
- 日期：2026-07-29
- 产品契约：`resume-assessment-and-optimization`

## Objective

将简历中心优化为清晰、紧凑的双栏工作台，提升上传、版本切换、六维评分、关键词、
问题证据和优化稿编辑的可读性与操作效率。

## Non-goals

- 修改简历解析、评估或优化模型；
- 改变上传、重新评估、保存、导出和删除的业务规则；
- 修改数据库或用户文件。

## Acceptance criteria

- 使用仓库有效设计 Token，修复卡片、表单和选中态样式失效；
- 左栏明确区分上传入口、隐私说明和简历版本，状态使用中文；
- 右栏以文件信息、六维评分、关键词、问题证据和优化稿分区展示；
- 问题证据适合多条扫描，优化稿表单层级清楚且导出限制可见；
- 桌面端保持合理阅读宽度，移动端单栏且无横向溢出；
- 简历页面样式按路由加载，不突破主应用 Bundle 预算；
- 简历专项与完整 Harness、桌面/移动端、无障碍和视觉检查通过；
- 部署后健康、页面和按需资源验证通过。

## Progress

- [x] 检查用户截图、组件、样式和当前测试；
- [x] 调整页面信息架构、状态文案和报告组件；
- [x] 重写页面样式并补充 ready 报告验收；
- [x] 运行浏览器、前端和完整 Harness；
- [x] 部署并记录生产验证。

## Findings

- 原样式引用未定义的 `--border`、`--surface`、`--background`、`--text` 和
  `--accent`，导致关键卡片、输入框和选中态声明失效。
- 当前 E2E 只覆盖上传后的处理中状态，没有覆盖评分、问题证据和优化稿布局。
- Vue 响应式代理不能直接传给 `structuredClone`，原实现会使完整优化稿静默缺失；
  改为克隆 `toRaw` 后的数据，并通过 ready 报告用例覆盖。
- `agent-browser` CLI 在当前环境不可用；使用仓库 Playwright、截图人工检查、
  Axe 和横向溢出断言完成等价的桌面/移动浏览器验证。

## Verification

- `pytest -q`：224 passed，2 skipped；
- 前端类型检查、18 项单元测试、生产构建和 Bundle 预算通过；
- 简历专项 Playwright：桌面/移动共 4 项通过，包含 Axe 严重级检查；
- 全量 Playwright：本次简历用例全部通过；一项无关面试题用例因测试附件流偶发
  损坏失败，随后桌面/移动单独复跑 2 项通过；
- 生产镜像：`sha256:75d4442060ba4b7fb8e9c95e02e1f6cdf20ab657a179c59f86f70138639f599a`；
- 生产验证：`/health` 为 `ok`、`/ready` 为 `ready`、`/resumes` 为 200，
  App 容器健康且重启次数为 0；
- 发布记录：`production-20260729T1752Z-resume-ui`。

## Rollback

仅涉及 Vue 模板、CSS 和前端测试；可恢复镜像
`interview-agent-app:rollback-resume-ui-20260729T1746Z`，无迁移和数据回写。
