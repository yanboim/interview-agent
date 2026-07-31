# 简历评估与优化

- 状态：completed；功能默认关闭，已通过完整 Harness
- 日期：2026-07-28
- 负责人：产品、后端、前端、AI质量和平台负责人
- 产品契约：`resume-assessment-and-optimization`
- 前置设计：
  - [用户敏感文件与异步处理](../../design-docs/user-sensitive-file-processing.md)
  - [简历与面试训练闭环](../../design-docs/resume-interview-review-loop.md)

## Objective

交付普通用户简历上传、异步解析与评估、事实受控的逐项改写、完整网页优化稿和
DOCX 导出，同时建立后续真实面试音频可复用的用户文件与后台任务底座。

## Non-goals

- OCR、图片简历、PDF 导出或原版式复刻；
- 职位搜索、自动投递或招聘流程；
- 简历定向面试和面试复盘；
- 将用户简历导入管理员知识库或 Qdrant；
- 自动补造用户未提供的事实。

## Acceptance criteria

- 当前用户可以上传合法 PDF/DOCX，并在刷新后查看处理状态和历史；
- 非法格式、伪装内容、损坏文件、扫描 PDF 和超限文件得到安全错误；
- 分析使用 JD 快照或岗位兜底，返回稳定的结构化报告；
- 每条改写有来源证据，新增事实和占位符阻止导出；
- 用户可编辑优化稿，版本冲突不会覆盖较新的编辑；
- DOCX 只由已确认的结构化稿生成；
- 删除清理原件、分析和导出产物，跨用户操作全部拒绝；
- Worker 崩溃、重试或迟到提交不会产生两份正式结果；
- 备份/恢复、隐私、可访问性和完整 Harness 验收通过。

## Public interfaces

```text
POST   /api/resumes
GET    /api/resumes
GET    /api/resumes/{resume_id}
POST   /api/resumes/{resume_id}/analyses
PATCH  /api/resume-analyses/{analysis_id}/draft
GET    /api/resume-analyses/{analysis_id}/export.docx
DELETE /api/resumes/{resume_id}
```

创建上传和重新分析要求 `Idempotency-Key`。编辑请求携带 `expected_revision`。
新 API 只使用认证身份，不接受 `user_id` 授权字段。

## Task breakdown

### R1. 契约、Schema 与评估 Fixture

- [x] 固化上传格式、大小、状态、错误码和响应 Schema；
- [x] 定义简历报告、问题、证据、优化稿、事实警告和编辑版本 Pydantic 模型；
- [x] 创建不含真实个人信息的 PDF/DOCX 合成 Fixture；
- [x] 创建岗位/JD、简历事实和期望问题的 AI 评估集；
- [x] 为新设置、Prompt 和结构化 Schema 分配版本。

完成条件：契约评审通过，Fixture 能覆盖正常、空内容、扫描件、损坏和事实冲突。

### R2. 数据库与用户文件存储

- [x] 设计并迁移 `resume_documents`、`resume_analyses` 及约束、索引；
- [x] 实现用户文件存储接口和文件系统适配器；
- [x] 实现流式上传、大小/签名/MIME 校验、哈希和原子提交；
- [x] 实现所有权读取、幂等删除和孤儿临时文件清理；
- [x] 为 API 与 Worker 配置共享卷和最小文件权限；
- [x] 扩展备份清单与恢复校验以覆盖用户文件。

完成条件：SQLite/PostgreSQL 迁移、跨用户负向、路径安全、删除竞争和备份测试通过。

### R3. 后台任务与应用服务

- [x] 扩展 Worker 处理器分派，保持 `knowledge_import` 行为兼容；
- [x] 新增只含资源 ID 的 `resume_analysis` 任务；
- [x] 实现数据库条件领取、所有者令牌、完成、失败和重试状态；
- [x] 确保模型调用不在数据库事务中；
- [x] 复用模型网关的分析、失败、耗时和成本指标，禁止正文标签；
- [x] 实现功能开关和依赖未就绪的安全错误。

完成条件：任务幂等、租约恢复、迟到所有者、死信和删除中任务测试通过。

### R4. 解析、评估与事实保护

- [x] 实现 PDF/DOCX 确定性文本和章节解析；
- [x] 检测无可提取文本的扫描 PDF 并返回专用错误；
- [x] 实现 JD 优先、用户资料 JD、岗位兜底及快照；
- [x] 通过模型网关生成版本化结构化报告和优化稿；
- [x] 校验结构化改写中的数字与待补充事实是否有来源证据；
- [x] 将新增事实、低置信内容和缺失信息转为警告或待补充项；
- [x] 实现编辑乐观并发和警告重新计算；
- [x] 实现标准单栏 DOCX 生成与导出门禁。

完成条件：解析单测、Schema 失败、模型异常、事实忠实度评估和 DOCX 内容测试通过。

### R5. API 与授权

- [x] 新增独立简历 Router 和应用服务，不向 `app/main.py` 添加业务规则；
- [x] 实现上传、列表、详情、重新分析、编辑、导出和删除；
- [x] 实现上传与重新分析幂等键内容冲突检查；
- [x] 统一 400/404/409/413/415/422/503 错误语义；
- [x] 确保所有读写、任务触发和下载均校验资源所有权；
- [x] 更新 API 文档生成源，禁止手工编辑 generated 文件。

完成条件：路由契约、认证、越权、并发和安全重放测试通过。

### R6. 前端简历中心

- [x] 增加 `/resumes/:resumeId?` 路由、导航和深链恢复；
- [x] 实现上传、格式说明、JD 选择和外部模型数据提示；
- [x] 实现历史列表、进度轮询、失败详情与重试；
- [x] 实现分数、关键词差距、问题、证据和建议展示；
- [x] 实现完整稿编辑、乐观冲突恢复和待补充项处理；
- [x] 实现事实警告和 DOCX 下载；
- [x] 覆盖桌面、移动端、键盘和严重无障碍问题检查。

完成条件：前端类型、单测、构建、Bundle 和 Playwright 核心流程通过。

### R7. 发布与文档闭环

- [x] 默认关闭功能开关，先部署迁移和兼容新任务的 Worker；
- [x] 用合成文件演练上传、处理、删除、备份和恢复；
- [x] 更新 PRD、架构、数据字典、API、配置、运维和隐私当前态文档；
- [x] 运行简历离线 AI 评估并记录不含用户数据的结果；
- [x] 运行 `make harness-check`；
- [x] 将功能契约改为 `passing` 并引用真实测试；
- [x] 完成后将本计划移动到 `completed/`。

## Verification plan

- 聚焦检查：解析、文件存储、简历服务、授权、迁移、Worker、DOCX；
- AI检查：事实忠实度、问题召回、JD 匹配和结构化输出成功率；
- E2E：上传到导出、失败重试、冲突、删除、移动端和可访问性；
- 全量门禁：`make harness-check`。

## Rollout and rollback

按“迁移与 Worker → API → 前端 → 功能开关”顺序部署。回滚先关闭开关，再回滚应用；
保留新表和文件，不执行降级迁移或批量删除。旧版本不得消费无法识别的新任务。

## Progress

- [x] 产品范围和关键决策完成；
- [x] 目标架构和任务拆解完成；
- [x] 上传、异步分析、事实保护、编辑和 DOCX 导出完成；
- [x] 用户文件备份恢复、离线评估和功能开关完成；
- [x] `make harness-check`：后端 199 passed/2 skipped，前端 16 passed，
  Playwright 18 passed。

## Decisions and findings

- 首版仅支持可提取文本的 PDF 与 DOCX；扫描件返回明确错误，不隐式引入 OCR。
- 模型只生成结构化稿，导出由本地 DOCX 渲染器完成；含无来源数字或待补充项时拒绝导出。
- 用户文件与管理员知识库完全隔离，备份以逐文件 SHA-256 清单验证。
- 沙箱内 Playwright 无法连接本地测试服务；在获批的本地网络环境运行后全部通过。
