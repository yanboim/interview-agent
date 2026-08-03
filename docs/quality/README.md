# 质量体系

- [测试策略](TEST-STRATEGY.md)
- [业务验收测试](ACCEPTANCE-TESTS.md)
- [质量门禁](QUALITY-GATES.md)
- [性能测试](PERFORMANCE-TESTING.md)
- [安全测试](SECURITY-TESTING.md)
- [AI与RAG评估](AI-EVALUATION.md)
- [可访问性测试](ACCESSIBILITY-TESTING.md)
- [兼容性矩阵](COMPATIBILITY-MATRIX.md)

具体命令和外部依赖见[测试与验证指南](../testing.md)。AI专项数据和报告位于
`eval/`，机器可读产品状态位于
[`feature-contract.json`](../product-specs/feature-contract.json)。
项目级故障注入与恢复场景位于[`dynamic-audit.json`](dynamic-audit.json)，只能在
明确的非生产测试环境中通过 `agent-fault-injection-tester` 执行。
