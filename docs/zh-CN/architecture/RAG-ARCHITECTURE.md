# RAG架构

## 导入与发布

```text
knowledge files
  -> decode and validate
  -> Markdown-aware chunking
  -> stable chunk_id + heading context
  -> Dense embedding + sparse representation
  -> new versioned Qdrant collection
  -> structural validation
  -> optional retrieval regression gate
  -> atomic serving-alias switch
```

候选版本命名使用配置集合前缀和版本后缀。首次成功发布前可读取旧集合；成功后稳定
别名成为服务目标。

## 检索

```text
query
  -> resolve physical collection behind alias
  -> dense/sparse hybrid candidates
  -> dense relevance rejection
  -> optional lexical / cross-encoder / LLM rerank
  -> final K chunks
  -> answer context + traceable sources
```

缓存键包含物理集合名称，因此别名切换自然进入新缓存命名空间。

## 正确性和失败

- 上传或验证失败只删除新候选，不删除服务版本；
- 发布锁在配置Redis时跨实例所有者保护，Redis失败时发布失败关闭；
- 别名切换使用一个原子Qdrant别名操作；
- 回滚仅允许存在且符合受管理前缀的版本；
- 回滚不删除离开的版本；
- Embedding模型或维度改变后必须重建知识集合。

## 数据与隐私

Embedding会把知识分块发送到配置的Embedding服务。LLM重排会把候选正文发送到
模型提供方，默认关闭。任何启用都需要确认知识内容允许发送给该提供方。

## 评估

- 固定问题集：Dense/Hybrid相关性；
- 稳定 `chunk_id` 数据集：Top-K、MRR和nDCG；
- 回答数据集：引用覆盖与忠实度；
- 发布门禁：可按配置在导入后阻止低于阈值的候选。

实现决策见
[Qdrant版本发布设计](../design-docs/qdrant-versioned-publication.md)。
