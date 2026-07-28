# 依赖管理

## Python

- `requirements.in`是人工依赖输入；
- `requirements.txt`是Python 3.12哈希锁；
- 使用 `make lock-python` 重新生成并盖章；
- 安装使用 `pip install --require-hashes -r requirements.txt`。

## Frontend

- `frontend/package.json`定义直接依赖；
- `package-lock.json`锁定完整图；
- CI使用 `npm ci`；
- 工具链升级同时运行类型、单元、Build、Bundle和E2E。

## 容器与Actions

- 运行镜像使用版本和Digest；
- GitHub Action至少使用明确Release主版本，并由Dependabot和评审更新；
- 不使用 `latest` 作为生产输入。

## 更新流程

1. 阅读Changelog和安全公告。
2. 单独更新相关依赖，避免混入业务变更。
3. 重新生成Lock/Stamp。
4. 运行可复现检查、测试、审计和镜像扫描。
5. 记录破坏性变化、迁移和回滚。

不得通过关闭审计、降低严重级别或移除安全控制来“修复”依赖门禁。
