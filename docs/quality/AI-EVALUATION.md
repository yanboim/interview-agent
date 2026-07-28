# AI与RAG评估

## 评估面

| 能力 | 数据/脚本 | 主要指标 |
|---|---|---|
| 检索 | `eval/questions.jsonl`, `evaluate_rag` | 命中、MRR、阈值拒绝 |
| 分块 | 分块标注集, `evaluate_chunks` | Top-K、MRR、nDCG |
| 回答 | `eval/answer_quality.jsonl`, `evaluate_answers` | 引用、支持声明、忠实度 |
| Agent路由 | 路由数据集, `evaluate_multi_agent` | 总体和分Agent准确率 |
| 面试评分 | 解析/报告测试和人工样本 | 结构有效、维度一致、可解释 |

## 变更触发

模型、Prompt、工具、路由、Embedding、分块、阈值、重排、知识内容或上下文策略变化
时运行受影响评估。

## 报告

保存数据集版本、Commit、配置、模型、时间、总体/分组指标和失败样本。Live调用记录
成本和数据外发审批。人工标注真值不能由同一个被评估模型自动替代。

## 门禁

阈值由基线和产品风险批准。知识发布可以启用nDCG门禁；低于门禁的候选不得切换
服务别名。降低阈值需要设计理由和评审。
