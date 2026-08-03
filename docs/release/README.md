# 发布文档

- [发布流程](RELEASE-PROCESS.md)
- [部署运行手册](DEPLOYMENT-RUNBOOK.md)
- [回滚运行手册](ROLLBACK-RUNBOOK.md)
- [环境说明](ENVIRONMENTS.md)
- [数据库发布](DATABASE-RELEASE.md)
- [知识库发布](KNOWLEDGE-RELEASE.md)
- [版本管理](VERSIONING.md)
- [发布说明模板](RELEASE-NOTES-TEMPLATE.md)

GitHub Release workflow先运行完整的`make harness-check`，只有静态契约、后端、
前端、构建预算和浏览器E2E全部通过后，制品打包Job才会开始。随后工作流构建镜像，
通过Trivy阻断仍有修复版本的高危或严重漏洞，再打包镜像Tar和SHA-256校验和，但不会
自动部署生产。实际环境发布仍需按部署运行手册执行并记录证据。
