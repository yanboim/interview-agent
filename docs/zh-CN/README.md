<!-- 本目录由 `python -m scripts.generate_chinese_docs` 生成；权威源文件见 `../` 和仓库根目录。 -->

# Interview Agent 文档中心

本目录覆盖从产品发现、原型、架构、开发、验证、发布到运行和复盘的完整生命周期。

## 简体中文镜像

当前生命周期清单中的每份文档都在 [`zh-CN/`](README.md) 中提供简体中文
版本。已经以中文编写的权威源自动镜像；英文叙述文档使用带源版本锁的人工翻译；
API、配置、数据字典和功能契约从实现生成中文参考。

```bash
make docs-generate
make docs-check
```

历史执行记录和 `knowledge/` 面试语料不是当前生命周期规范，不进入中文镜像。

## 按角色进入

| 角色/任务 | 建议入口 |
|---|---|
| 新接手工程师（循序渐进完整教程 + 速查参考 + cookbook） | [新工程师完整上手指南](../ONBOARDING-GUIDE.md) |
| 新接手工程师（精炼速查、14 节概览） | [开发、运维与使用接手手册](ENGINEERING-HANDOVER-MANUAL.md) |
| 想系统性补 Agent 工程基础（12 周课程） | [从零到企业级 Agent 工程课程](../enterprise-agent-engineering-course.md) |
| 产品负责人 | [产品愿景与PRD](product/README.md) |
| 产品/交互设计 | [信息架构、流程和原型](ux/README.md) |
| 架构师/后端开发 | [系统架构](architecture/README.md) |
| 前端/后端贡献者 | [开发指南](development.md)与[SDLC](sdlc/README.md) |
| 测试与质量 | [质量体系](quality/README.md) |
| 发布负责人 | [发布流程](release/README.md) |
| 运维与事故响应 | [运维手册](operations/README.md) |
| 安全与隐私评审 | [安全模型](security/README.md) |
| 项目负责人 | [项目治理](project/README.md) |
| Coding Agent | [AGENTS.md](root/AGENTS.md) |

## 文档体系

```text
docs/
├── product/         产品愿景、PRD、用户、功能与非功能需求
├── ux/              信息架构、用户流程、页面、原型和交互状态
├── product-specs/   机器可读功能契约
├── architecture/    系统、组件、领域、数据、Agent、RAG和API架构
├── design-docs/     持久技术决策与替代方案
├── sdlc/            开发流程、DoR、DoD和评审
├── exec-plans/      活动与已完成实施计划
├── quality/         测试策略、验收矩阵和质量门禁
├── release/         发布、部署、回滚和环境
├── reliability/     可靠性行为总览
├── operations/      日常运维、事故、备份和灾备
├── security/        信任边界、威胁、数据分级和隐私
├── project/         计划、风险、决策、责任和状态报告
├── generated/       只存放可复现生成的参考
├── zh-CN/           完整简体中文生命周期文档镜像
├── i18n/zh-CN/      需要人工维护的中文翻译源和版本锁
└── tech-debt-tracker.md
```

## 事实来源

发生冲突时使用以下优先级：

1. 可执行测试和数据库约束；
2. `product-specs/feature-contract.json`；
3. `ARCHITECTURE.md` 和已接受设计文档；
4. 产品、开发、发布和运行指南；
5. 历史路线图、完成报告和执行记录。

## 历史材料

- [`DEVELOPMENT_ROADMAP.md`](../../DEVELOPMENT_ROADMAP.md)：2026-07早期基础能力路线图；
- [`P0_P2_COMPLETION.md`](../../P0_P2_COMPLETION.md)：2026-07-25产品体验验收记录；
- [`plan.md`](../../plan.md)：项目早期构想和演进背景。

历史材料不作为当前行为或架构规范。当前行为以功能契约和测试为准。

文档职责、更新触发和评审规则见
[文档维护规范](documentation-guide.md)。

完整生命周期必需文件由
[`document-manifest.json`](../document-manifest.json)机器校验；API、配置和数据字典
由[`generated/`](generated/README.md)从源码生成。
