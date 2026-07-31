# 版本管理

## 应用与制品

正式Release采用不可变Git Commit/Tag、镜像名称和Digest。相同版本不得重新发布不同
内容。Changelog记录用户和运行影响。

## API

当前API没有公开版本前缀。兼容变化可增量发布；删除、重命名或语义破坏需要设计
记录、客户端迁移和发布说明。正式多客户端承诺前应引入API版本策略。

## 数据库

Alembic Revision是Schema版本。应用Release记录支持的Revision范围和目标Head。

## 知识与评估

物理Qdrant集合名称标识知识版本，稳定别名标识服务版本。评估报告记录数据集、配置、
模型和Commit。

## Prompt与模型

影响产品行为的Prompt、结构化输出和模型配置随源码版本管理。重大变化在发布说明中
标记并运行AI评估。
