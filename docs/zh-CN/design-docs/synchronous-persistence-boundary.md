# 同步持久化边界

## 上下文

应用同时为SQLite和PostgreSQL使用同步SQLAlchemy Core。FastAPI适配器曾各自决定何时
调用 `asyncio.to_thread`，`ConversationStore` 则通过一个 `threading.RLock` 串行化
几乎全部操作。线程切换重复，而且锁只能在单进程内串行化，无法保证跨副本生产正确性。

## 决策

保留同步SQLAlchemy Core，采用：

```text
异步API适配器
  -> SyncExecutor.run(应用服务或Store事务脚本)
      -> 同步SQLAlchemy Engine
          -> 每次变更一个engine.begin()
          -> 每次读取一个engine.connect()
```

`SyncExecutor` 是API层进入Worker线程池的唯一桥梁。Store方法保持同步事务脚本，事务在
方法内部开始和结束。包含外部模型调用的应用流程使用短暂持久领取和完成事务，网络I/O
期间不保持连接或事务。

条件更新、唯一约束、外键、幂等键和领取所有者Token定义并发正确性。进程锁可以保护
一次性本地Schema初始化，但不能包围业务读写，也不属于任何用例正确性论证。

## 后果

- Event Loop不执行阻塞数据库工作。
- Store方法边界明确显示事务所有权。
- 并发测试验证数据库行为，而非Python串行化。
- PostgreSQL是生产并发权威；SQLite作为本地/测试适配器保留其原生写串行化。
- 将来迁移异步SQLAlchemy只替换执行器和仓储实现，不改变领域状态转换语义。
