# 产品规格

`feature-contract.json` 是用户可见产品行为的机器可验证索引。它补充而不替代详细测试
和API Schema。

每项功能包含：

- 稳定且唯一的 `id`；
- 类别和行为说明；
- 有序验收步骤；
- 带可执行仓库证据的 `passing` 状态，或带明确缺口链接的 `planned` 状态。

产品行为变化时必须在同一变更中更新契约。没有可执行验证引用的实现不得标记为
`passing`。编辑后运行 `make harness-static`。
