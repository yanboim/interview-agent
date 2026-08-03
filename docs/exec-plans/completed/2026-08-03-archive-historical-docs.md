# Archive historical root documents into docs/history/

- Status: completed
- Date: 2026-08-03
- Owner: repository maintainers

## Objective

将三份自述"历史/已废弃"的根目录文档迁入 `docs/history/`，统一归档，
保持根目录只承载当前事实来源与必要的入口文档。

迁移对象：

- `DEVELOPMENT_ROADMAP.md`（2026-07 早期基础能力路线图，自述历史）
- `P0_P2_COMPLETION.md`（2026-07-25 发布验收记录，自述历史）
- `plan.md`（项目早期构想与演进背景，自述历史）

## Non-goals

- 移动 6 个根入口文档（`README.md`、`AGENTS.md`、`ARCHITECTURE.md`、
  `CHANGELOG.md`、`CONTRIBUTING.md`、`SECURITY.md`）——它们被 harness
  契约、文档生成器硬编码与中文镜像三重约束钉在根目录。
- 将三份历史文档纳入 `document-manifest.json` 或生成中文镜像——已废弃内容
  仅作存档，不承担翻译与生命周期维护负担。
- 重写历史文档正文——仅迁移位置，保留其自述历史声明。

## 决策与背景

`docs/exec-plans/completed/2026-07-27-lifecycle-documentation.md:75-76` 曾以
"链接稳定性"为由决定保留这三份于根目录。随着文档体系成熟、`docs/history/`
作为归档目录落地，该权衡不再成立：归档目录语义更清晰，且三者不在任何清单
或生成器列表中，迁移后链接可一次性同步更新并通过 harness 校验。本次变更
推翻该旧决策。

## 受影响的契约与架构规则

- `tests/test_harness_contract.py::test_repository_markdown_links_resolve`：
  所有相对 Markdown 链接必须解析，迁移后必须同步更新引用方能在同一次变更中通过。
- `test_required_harness_documents_exist` 与 `test_lifecycle_document_manifest_is_complete`：
  这三份文档不在其校验集合中，迁移不影响这两项断言。

## 验收标准

- `docs/history/` 下存在 README + 三份文档，共 4 个文件。
- 根目录不再出现这三份文档。
- 仓库内无指向旧根路径的残留 Markdown 链接。
- `make docs-check` 与 `make harness-static` 通过。

## Work plan

1. 新建 `docs/history/` 与 `docs/history/README.md`（归档说明）。
2. 迁移三份文档（保留文件名）。
3. 更新 `docs/README.md` 与 `docs/zh-CN/README.md` 的"历史材料"链接。
4. 更新 2026-07-27 lifecycle exec plan 第 75-76 行的叙述，使其反映新位置。
5. 运行 `make docs-check` 与 `make harness-static`，grep 复查无残留引用。
6. 验证通过后将本计划移入 `completed/`。

## Progress

- [x] 创建 `docs/history/` 与 README。
- [x] 迁移三份文档。
- [x] 更新 README 链接（中文 + 英文）。
- [x] 更新 2026-07-27 exec plan 叙述。
- [x] `make docs-check` 通过。
- [x] `make harness-static` 通过。
- [x] 移入 `completed/`。

## Verification

```bash
make docs-check
make harness-static
```

Result on 2026-08-03：`docs-check` 三个生成器均报 "current"（生成文档、123 篇
中文镜像、mkdocs 配置无需同步）；`harness-static` 中 `test_harness_contract.py`
10 项全过（含链接解析与必需文档断言），`test_architecture.py`、
`test_reproducibility.py`、`test_structure_baseline.py` 共 20 项全过。grep 复查
无残留旧根路径 Markdown 链接。

## Rollback

将三份文档移回根目录，恢复 README 中的 `../` 链接，删除 `docs/history/`。
本次变更不触及应用代码、清单与生成器，回滚面小。
