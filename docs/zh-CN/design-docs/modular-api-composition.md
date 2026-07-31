# 模块化API组合

## 上下文

`app/main.py` 曾超过2,100行，同时负责依赖构建、中间件、DTO校验、授权辅助、文件
操作、模型编排和全部HTTP路由。无关变更会在同一模块冲突，路由适配器也会直接依赖
组合层全局对象。

## 决策

引入：

```text
app/api/
  runtime.py       单个已配置依赖容器
  schemas.py       传输DTO
  security.py      身份和角色强制
  agent_io.py      消息/来源传输转换
  routers/
    auth.py
    profile.py
    admin.py
    chat.py
    conversations.py
    interviews.py
    learning.py
```

组合根构建具体适配器和服务、配置一次Runtime、安装中间件并包含每个路由。路由模块
可以依赖API辅助、应用服务和Runtime暴露的领域/基础设施接口，但不得导入 `app.main`。

为兼容现有内部测试或脚本，`app.main` 可以暂时导出DTO和选定处理器的别名。它们只是
别名，不会把路由所有权重新交给组合根。

## 后果

- 依赖构建仍在一个位置保持显式。
- 路由测试可替换单个Runtime字段，无需导入隐藏组合全局对象。
- Runtime容器是进程级配置，不是正确性锁或可变请求状态。
- 模型编排可按领域继续提取到应用服务，无需编辑组合根。
