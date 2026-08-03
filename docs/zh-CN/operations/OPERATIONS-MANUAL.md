# 日常运维手册

## 每日/每班检查

- 应用实例、Worker和依赖均处于预期状态；
- `/health` 与 `/ready` 成功；
- 请求错误、延迟和依赖错误无异常增长；
- Redis任务无持续积压或反复重试；
- PostgreSQL和Qdrant容量有余量；
- 用户文件卷容量、权限和孤儿文件检查正常；
- 最近备份成功且验证计划未过期；
- 外部模型错误、Token使用和成本无异常。
- Agent分组质量门禁、确认/工作流完成率、反馈候选积压和模型路由阶段符合预期。

## 服务状态

```bash
docker compose ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
docker compose logs --since=15m app worker
```

日志输出前确认不会包含Secret或私人内容。生产应通过集中日志系统而不是长期进入
容器读取。

## 后台任务

Worker处理 `knowledge_import`、`resume_analysis`、`interview_transcription` 和
`interview_review_analysis`。任务使用领取、租约、心跳、确认、失败重试和最大尝试
次数。管理员系统资源中心展示带TTL的Worker进程心跳。

持续失败任务应按任务类型检查输入、用户文件卷、模型/转写提供方、Embedding、
Qdrant和回归门禁，不要通过删除队列掩盖原因。

## 知识版本

定期检查：

- 稳定别名当前目标；
- 最近发布结果；
- 历史版本数量和磁盘占用；
- 回归报告和Embedding配置。

删除历史版本前必须确认它不是当前目标、不是计划回滚目标，并遵循批准的保留策略。

## 数据库

- 观察连接、查询延迟、存储和备份；
- 迁移只在发布流程执行；
- 不在生产运行 `create_all`；
- 不直接手改业务表修复应用状态，除非有批准脚本、备份和验证。

## 用户文件与外部转写

- API与Worker必须挂载同一 `USER_FILES_DIR` 持久卷；
- 监控卷容量、无法打开的存储键和无数据库引用的孤儿文件；
- 音频转写仅在功能开关、供应商配置和用户本次确认同时成立时启用；
- 逐字稿成功持久化后确认音频已删除；失败音频只用于受控重试或用户删除；
- 恢复时按同一批次核对数据库资源记录与文件清单。

## 部署发布台账

Canary和生产验证完成后使用 `python -m scripts.record_release` 幂等记录环境、版本、
结果、验证和回滚证据。Git提交存在不代表已部署；管理员页面中的发布台账是环境事实
读取模型。

## Agent运行与模型路由

- 检查 `agent_runs`/`agent_steps` 的failed、长期claimed和恢复次数，不直接改表；
- 只对过期领取运行管理员恢复；只读/模型步骤可自动重试，命令步骤依赖幂等结果重放；
- 原应用所有者停止且聊天回合超过批准阈值后，运行
  `python -m scripts.recover_stale_chat_turns --older-than-seconds 600 --limit 100 --confirm`；
  记录目标、阈值、恢复数量和重试结果，旧Token的迟到提交必须被拒绝；
- 监控公开搜索DLP拒绝、确认过期/放弃、声明证据覆盖和零容忍安全失败；
- 模型路由按off、internal、canary、production推进；Canary报告需同时满足分组质量、
  完成率、p95延迟和单次完成训练成本门禁；
- 回滚路由时把阶段设为off恢复Supervisor和默认模型路径，不修改历史生成版本；
- 评估、简历分析和面试复盘出现未批准模型回退时按安全故障处理。

## 维护记录

每次配置、迁移、知识发布、恢复、Secret轮换或容量清理记录操作者、目标、时间、
原因、命令/版本、结果和回滚证据。
