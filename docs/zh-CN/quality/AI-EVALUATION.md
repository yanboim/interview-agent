# AI与RAG评估

## 评估面

| 能力 | 数据/脚本 | 主要指标 |
|---|---|---|
| 检索 | `eval/questions.jsonl`, `evaluate_rag` | 命中、MRR、阈值拒绝 |
| 分块 | 分块标注集, `evaluate_chunks` | Top-K、MRR、nDCG |
| 回答 | `eval/answer_quality.jsonl`, `evaluate_answers` | 引用、支持声明、忠实度 |
| Agent路由 | 路由数据集, `evaluate_multi_agent` | 总体和分Agent准确率 |
| Agent应用栈 | `eval/agent_quality_suite.v1.json`, `evaluate_agent_stack` | 分组通过率、零容忍失败、耗时、成本 |
| 面试评分 | 解析/报告测试和人工样本 | 结构有效、维度一致、可解释 |
| 简历评估 | `eval/resume_analysis.jsonl`, `evaluate_resumes` | Schema成功、关键词差距召回、问题类别召回、事实门禁 |
| 简历定向出题 | `eval/resume_interview_questions.jsonl`, `evaluate_resume_interviews` | 证据关联、题型覆盖、重复率、隐私违规 |
| 面试复盘 | `eval/interview_reviews.jsonl`, `evaluate_interview_reviews` | 问答配对、结构成功、只评价候选人 |

## 变更触发

模型、Prompt、工具、路由、Embedding、分块、阈值、重排、知识内容或上下文策略变化
时运行受影响评估。

简历评估的离线合成集可用以下命令运行，不调用外部模型，也不包含真实个人信息：

```bash
python -m scripts.evaluate_resumes \
  --output eval/reports/resume-analysis-baseline.json
```

该离线集验证候选结构和确定性事实门禁；更换模型或 Prompt 时仍需在获批环境运行人工标注
的 Live 样本，并单独记录成本和外发审批。

## 报告

保存数据集版本、Commit、配置、模型、时间、总体/分组指标和失败样本。Live调用记录
成本和数据外发审批。人工标注真值不能由同一个被评估模型自动替代。

## 门禁

阈值由基线和产品风险批准。知识发布可以启用nDCG门禁；低于门禁的候选不得切换
服务别名。降低阈值需要设计理由和评审。

默认CI运行230例冻结Agent应用栈语料，不调用外部模型。任何隐私泄露、未授权变更、
伪造来源或跨用户失败都会阻断门禁。模型路由只有在报告同时满足质量、完成率、p95延迟、
单次完成训练成本和零容忍安全指标后，才能从内测推进到金丝雀与生产；`off` 必须始终
能够恢复保留的Supervisor路径。
