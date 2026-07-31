# 可复现构建输入

## Python

`requirements.in` 声明直接兼容意图。`requirements.txt` 是为CPython 3.12 Linux
生成的Lock，包含精确传递版本和制品哈希。Runtime、CI和发布构建使用
`pip --require-hashes` 安装它，绝不直接解析宽泛输入文件。

Lock头包含 `requirements.in` 的SHA-256。仓库验证器无需联网即可检查头、精确Pin、
哈希、Dockerfile安装命令和CI安装命令。

## 镜像

所有外部Dockerfile和Compose镜像引用同时包含可读、非 `latest` 的版本Tag和
OCI Linux/amd64 Manifest Digest。即使上游移动Tag，Digest变化也会在评审中可见。
生产当前面向Linux/amd64；其他架构需要独立评审的Digest集合。

## 更新流程

1. 编辑 `requirements.in` 中的直接意图，或选择经评审的镜像版本。
2. 在规定Python 3.12环境重新生成Lock。
3. Stamp并运行离线可复现性验证器。
4. 评审直接/传递版本与哈希，或镜像Digest变化。
5. 运行依赖审计和 `make harness-check`。

Dependabot可以提出更新，但不能绕过这些门禁。
