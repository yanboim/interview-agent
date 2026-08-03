# 文档维护指南

## 目的

文档是变更的一部分，不是事后补充物。维护者应能仅通过文档识别当前行为、证据、
运维影响和下一步安全动作，不需要从源码历史重新推断意图。

## 文档类型

| 文档 | 负责内容 | 更新触发 |
|---|---|---|
| `README.md` | 产品概览、快速开始、主要运维入口 | 安装、支持流程或顶层命令变化 |
| `ARCHITECTURE.md` | 运行上下文、模块边界、正确性规则 | 依赖或正确性边界变化 |
| `product-specs/feature-contract.json` | 可验证用户行为及状态 | 行为或可执行证据变化 |
| `design-docs/*.md` | 持久技术决策及后果 | 重要决策提出、接受、替代或拒绝 |
| `exec-plans/active/*.md` | 进行中工作、决策和验证 | 非简单工作推进或产生发现 |
| `exec-plans/completed/*.md` | 历史实施和验证记录 | 计划满足验收标准 |
| `reliability/` | 依赖失败、运行和恢复 | 拓扑、健康、备份、回滚或告警变化 |
| `security/` | 信任边界和安全不变量 | 认证、授权、Secret、外部数据流或暴露变化 |
| `product/` | 愿景、用户、PRD、范围、业务规则和NFR | 产品意图、范围、规则或成功标准变化 |
| `ux/` | 信息架构、旅程、原型和状态 | 导航、页面、交互或恢复变化 |
| `architecture/` | 系统、领域、数据、Agent、RAG和API设计 | 组件、所有权、协议或数据流变化 |
| `sdlc/` | 就绪、实施、评审和完成流程 | 交付治理或评审门禁变化 |
| `quality/` | 测试策略、验收和质量门禁 | 验证范围或发布证据变化 |
| `release/` | 环境、部署和回滚 | 打包、迁移、提升或回滚变化 |
| `operations/` | 日常运行、事故、备份和灾备 | 运维过程或恢复行为变化 |
| `project/` | 里程碑、风险、决策、职责和状态 | 跨域范围、负责人或交付风险变化 |
| `tech-debt-tracker.md` | 重复性边界问题的优先级 | 技术债发现、调整、完成或替代 |
| `generated/` | 仅可复现参考 | 源发生变化并重新运行生成器 |

源码注释解释局部意图和约束，不能替代跨模块仓库文档。

## 必需元数据

执行计划包含状态、日期、负责人、目标、非目标、验收标准、进度、验证和回滚。

设计文档包含上下文、决策、替代或拒绝方案、后果、适用时的迁移以及验证。尚未实现的
决策必须明确标注，并链接活动计划或技术债。

Runbook必须说明前置条件、安全检查、操作步骤、预期结果、回滚和升级条件。文档不得
包含真实凭据、用户数据、私人知识正文或数据库Dump。

## 生命周期

1. 行为变化时在同一变更中更新文档。
2. 活动计划放在 `exec-plans/active/`，随工作进展记录发现。
3. 只有每个验证引用都存在且执行了所声称行为，产品功能才能标记为 `passing`。
4. 计划通过全部验收标准后才能移入 `exec-plans/completed/`，同时保留决策和失败方案。
5. 用最新内容替换矛盾旧内容；被替代设计应标明状态并链接新决策。

## 编写与链接

- 当前行为使用现在时，目标行为明确标记为计划。
- 使用仓库相对链接，确保本地和Code Review均可工作。
- 链接单一事实来源，避免重复配置表和命令序列。
- 命令使用可复制代码块，并注明是否具破坏性、产生费用、依赖凭据或外部服务。
- 优先引用测试、迁移、评估数据集或带生成命令的输出等可执行证据。
- Secret只使用占位符；`.env.example` 记录配置名，`app/config.py` 是实现事实来源。

## 评审清单

- 文档是否区分已实现、已规划和历史行为？
- 命令是否能从仓库根目录正确运行？
- 内部链接是否可解析？
- 安全和破坏性操作警告是否明确？
- 行为变化是否同步功能契约、设计记录、Runbook或技术债？
- `make harness-static` 是否通过？

## 自动完整性

`docs/document-manifest.json` 按生命周期列出必需文档。
`tests/test_harness_contract.py` 验证每项存在且唯一。API路由、Settings和关系元数据通过
以下命令生成：

```bash
python -m scripts.generate_docs
python -m scripts.generate_docs --check
```

完整中文镜像通过以下命令生成和验证：

```bash
python -m scripts.generate_chinese_docs
python -m scripts.generate_chinese_docs --check
```

英文源发生变化而人工中文稿未更新、中文文件缺失或生成参考漂移，都会使Harness静态
门禁失败。

## 文档网站

生命周期文档还会发布为支持搜索的中英文 MkDocs Material 网站。网站导航由
`docs/document-manifest.json` 生成，因此始终与生命周期清单同步，不能手工编辑。
生成的 `mkdocs.yml`、`docs/experience` → `docs/ux` 别名符号链接（用于避免 `ux`
与国际化插件的双字母语言代码冲突）以及 `site/` 构建输出均为可再生构建产物。

```bash
make docs-site    # 重新生成 mkdocs.yml 和别名符号链接
make docs-serve   # 在 http://127.0.0.1:8001 本地预览网站
```

范围和行为：

- 网站仅覆盖 `docs/`。仓库根入口文档（`README.md`、`ARCHITECTURE.md`、
  `AGENTS.md`、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`）不在
  `docs_dir` 中，不由网站渲染；请直接在仓库中阅读。已完成执行计划、`knowledge/`
  和 `eval/` 同样不进入网站。
- 英文内容来自 `docs/`；简体中文内容来自 `make docs-generate` 生成的
  `docs/zh-CN/` 镜像。运行 `make docs-serve` 前先刷新镜像，确保中文内容最新。
- 文档保留指向根文件、`tests/`、`eval/` 和 `.env.example` 的仓库相对链接。
  这些目标不在网站内，因此网站允许其缺失（`validation not_found: ignore`），
  而不重写源文档。
- 新文档需要加入 `docs/document-manifest.json`；随后运行 `make docs-site` 刷新
  `mkdocs.yml`。

`.github/workflows/docs.yml` 会重新生成参考文档和中文镜像，校验 `mkdocs.yml`
与清单一致，以严格模式构建网站，并在 `main` 变更时部署到 GitHub Pages。
