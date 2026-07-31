# 生成参考

本目录只存放可复现生成的文档，例如Schema或API参考。每个生成制品必须标明来源和
重新生成命令，不得手工编辑生成输出。

当前参考：

- `api-routes.md`：组合根和路由模块中的FastAPI装饰器；
- `configuration.md`：`app.config.Settings`；
- `data-dictionary.md`：SQLAlchemy表元数据。

生成英文权威参考：

```bash
python -m scripts.generate_docs
```

生成完整中文镜像：

```bash
python -m scripts.generate_chinese_docs
```

只验证、不写入：

```bash
python -m scripts.generate_docs --check
python -m scripts.generate_chinese_docs --check
```
