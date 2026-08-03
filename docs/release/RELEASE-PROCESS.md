# 发布流程

## 发布输入

- 已评审并合并的源码；
- 通过的质量门禁；
- 版本范围和发布说明；
- 数据库、配置、知识库和外部依赖变化；
- 部署、验证和回滚负责人。

## 1. 发布准备

1. 冻结候选Commit并确认工作区无未说明变更。
2. 运行 `make harness-check`。
3. 运行可复现输入检查和依赖/镜像安全检查。
4. 确认Alembic当前Head、迁移顺序和历史数据影响。
5. 对生产数据库和知识版本准备可恢复备份。
6. 审查环境变量、Secret文件和第三方额度。
7. 编写发布说明、风险和回滚触发条件。

## 2. 构建制品

Release workflow通过Tag或手动选择Canary/Production通道运行，构建Docker镜像，
在导出前用Trivy阻断仍有修复版本的高危或严重漏洞，然后导出Tar并生成SHA-256。
制品保留期当前为14天。

制品校验：

```bash
sha256sum -c interview-lab-image.sha256
```

不要在目标环境重新拼装不同依赖的镜像。

## 3. Canary

部署到Canary后验证：

- Migration完成且Revision正确；
- `/health` 和 `/ready`；
- 登录、聊天、面试和管理员只读冒烟；
- Worker任务领取和知识状态；
- 错误率、P95延迟、数据库/Redis/Qdrant/模型依赖指标；
- 日志无秘密、迁移错误或重复业务结果。

Canary观察窗口和量化阈值需由具体版本发布计划确认。

## 4. Production

获得环境审批后使用同一制品扩大部署。按
[部署运行手册](DEPLOYMENT-RUNBOOK.md)执行，禁止临时修改未进入制品的文件。

## 5. 关闭发布

- 记录Commit、Tag、镜像摘要、迁移Revision和知识版本；
- 记录发布前后核心数据计数和健康证据；
- 使用 `scripts.record_release` 写入管理员发版记录；
- 关闭执行计划；
- 对残余风险建立后续项。

任何失败达到预定义触发条件时停止扩大并执行
[回滚运行手册](ROLLBACK-RUNBOOK.md)。
