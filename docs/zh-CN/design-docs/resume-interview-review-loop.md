# 简历与面试训练闭环

- 状态：Accepted / Implemented
- 日期：2026-07-28
- 负责人：产品、后端、AI质量和前端负责人
- 关联产品规格：
  [简历驱动的面试训练与面试复盘](../product/RESUME-INTERVIEW-REVIEW.md)

## Context

系统在原有通用模拟面试之外，已提供简历领域对象、简历定向面试、真实面试逐字稿
和模型改写内容的事实追踪。三个能力共享用户目标和能力结果，但保持独立状态机。

## Decision

### 领域边界

保留三个独立聚合：

```text
ResumeDocument
  -> ResumeAnalysis -> OptimizedResumeDraft

Interview
  -> InterviewTurn
  -> optional ResumeInterviewContext

InterviewReview
  -> TranscriptRevision
  -> InterviewReviewTurn
  -> ReviewReport
```

模拟面试继续使用现有 `interviews` 和 `interview_turns` 生命周期。真实面试使用
独立表，避免把已经发生的问答伪装成待提交的模拟面试回合。能力画像和学习任务在
查询层合并两类已评分结果，并保留 `mock`、`real` 来源。

### 数据模型

`resume_documents` 保存所有权、原件元数据、存储键、解析状态和时间戳。

`resume_analyses` 保存简历 ID、基准 JD/岗位快照、解析文本、结构化报告、优化稿、
事实警告、编辑版本、处理状态和 Prompt/模型版本。

`interviews` 增加可空的来源分析 ID 和最小化出题上下文快照。快照只包含岗位、
技能、项目主张、JD 差距和待核实点，不复制完整简历。

`interview_reviews` 保存输入类型、处理状态、逐字稿 JSON、逐字稿版本、确认版本、
报告、处理令牌和时间戳。`interview_review_turns` 保存提取后的问题、候选人回答、
四维评分、反馈和参考回答。

所有用户资源的主键或唯一约束包含服务端解析的 `user_id`；删除使用外键级联和文件
存储幂等清理。

### 简历分析

文档解析器只负责确定性文本和章节提取，不调用模型。应用服务在解析完成后通过统一
模型网关请求版本化结构化输出。

报告最少包含：

- 岗位匹配、完整性、相关性、表达、成果量化、ATS 可读性评分；
- JD 关键词覆盖和差距；
- 带严重级别、来源证据和行动建议的问题；
- 结构化完整优化稿；
- 待用户补充的问题和事实警告。

每个改写字段携带来源片段 ID。确定性校验比较公司、职位、日期、数字和关键技术
实体；模型新增且没有来源证据的事实进入警告。存在警告或占位符时导出服务拒绝生成
DOCX。用户保存编辑时提交 `expected_revision`，版本不一致返回冲突。

### 简历定向出题

开始面试时可选一个当前用户、状态为 `ready` 的简历分析。应用服务读取并保存
最小化上下文快照后再生成第一题，后续出题只读取该快照和已完成回合。

出题要求覆盖项目细节、技术决策、本人职责、量化结果、失败复盘和 JD 差距，且一次
只提出一个可评分问题。现有答案幂等领取、评分、下一题生成和提交逻辑保持不变。

删除简历后，不再允许从该分析开始新面试；历史面试的问题、回答和来源类型仍保留，
但不展示或恢复完整简历内容。

### 面试复盘

音频转写或文本输入先形成未确认逐字稿。片段结构为：

```text
segment_id, start_ms?, end_ms?, speaker, text
```

`speaker` 只允许 `interviewer`、`candidate`、`unknown`。用户修改片段会递增
`transcript_revision` 并清除确认状态。确认请求必须携带最新版本和幂等键。

分析服务将确认后的片段组合为问答回合，只评分候选人回答。无法可靠配对的片段保留
在报告附录，不强行生成评分。报告和回合在一个数据库事务中提交，失败不得产生半份
能力画像数据。

### API

简历：

```text
POST   /api/resumes
GET    /api/resumes
GET    /api/resumes/{resume_id}
POST   /api/resumes/{resume_id}/analyses
PATCH  /api/resume-analyses/{analysis_id}/draft
GET    /api/resume-analyses/{analysis_id}/export.docx
DELETE /api/resumes/{resume_id}
```

模拟面试：

```text
POST /api/interviews/start
  + optional resume_analysis_id
```

真实复盘：

```text
POST   /api/interview-reviews/audio
POST   /api/interview-reviews/text
GET    /api/interview-reviews
GET    /api/interview-reviews/{review_id}
PATCH  /api/interview-reviews/{review_id}/transcript
POST   /api/interview-reviews/{review_id}/confirm-and-analyze
POST   /api/interview-reviews/{review_id}/retry
DELETE /api/interview-reviews/{review_id}
```

上传、创建分析、确认分析等可重试写操作要求 `Idempotency-Key`。编辑逐字稿和优化稿
使用版本号乐观并发。

## Alternatives

### 将简历放入 Qdrant 私人知识库

拒绝。简历需要版本、事实校验、编辑、导出和删除语义，不是管理员发布的共享知识。

### 将真实面试导入现有模拟面试表

拒绝。现有回合包含待回答、领取和下一题生成状态，无法准确表达已经发生且需用户
确认的逐字稿。

### 删除简历时级联删除历史模拟面试

拒绝。历史训练是独立用户记录。删除操作会明确说明历史问题和回答仍需单独删除。

### 自动转写后立即评分

拒绝。说话人和文本错误会把面试官内容当作候选人回答，污染评分与能力画像。

## Consequences

- 能力画像聚合需支持来源维度并避免模拟与真实记录重复；
- Prompt、结构化 Schema 和评估数据集成为版本化产品行为；
- DOCX 导出依赖结构化稿而不是模型直接生成二进制；
- 用户修改逐字稿后必须重新确认和重新分析；
- 页面需要显示异步处理、事实警告、并发冲突和来源透明度。

## Migration and compatibility

- 新表通过 Alembic 创建；现有面试记录的来源默认为 `general`；
- 原 API 返回字段保持兼容，新来源字段为可选；
- 能力画像在没有真实复盘数据时保持现有结果；
- 功能开关关闭时前端不展示新导航入口，新路由返回明确不可用状态；
- 回滚应用版本前先关闭功能开关，不删除新表或用户文件。

## Verification

- 简历解析、结构化 Schema、事实忠实度和 DOCX 导出测试；
- 简历来源授权、快照稳定性和现有面试生命周期回归；
- 逐字稿版本冲突、确认门禁、问答配对和事务原子性测试；
- 能力画像/学习任务的来源合并和去重测试；
- 合成简历与逐字稿 AI 评估集；
- 桌面、移动端、无障碍和深链恢复 E2E；
- `tests/test_resume_features.py`、`tests/test_resume_interview_loop.py` 和
  `tests/test_interview_review_features.py` 提供后端行为证据；
- 前端组件与Playwright测试覆盖入口、深链和关键状态；
- `make harness-check` 是完整回归门禁。
