# 发布文档

- [发布流程](RELEASE-PROCESS.md)
- [部署运行手册](DEPLOYMENT-RUNBOOK.md)
- [回滚运行手册](ROLLBACK-RUNBOOK.md)
- [环境说明](ENVIRONMENTS.md)
- [数据库发布](DATABASE-RELEASE.md)
- [知识库发布](KNOWLEDGE-RELEASE.md)
- [版本管理](VERSIONING.md)
- [发布说明模板](RELEASE-NOTES-TEMPLATE.md)

GitHub Release workflow当前负责验证、构建、打包镜像Tar和SHA-256校验和，不会
自动部署生产。实际环境发布仍需按部署运行手册执行并记录证据。
