# 兼容性矩阵

| 层 | 当前基线 | 验证 |
|---|---|---|
| Python | 3.12 | CI、哈希锁和编译 |
| Node.js | 20 | CI和npm lock |
| 浏览器 | Chromium桌面、Pixel 7视口 | Playwright |
| 数据库 | SQLite本地/测试，PostgreSQL 17参考生产 | 单元、迁移、集成 |
| Redis | Redis 7 Alpine参考镜像 | 单元和显式集成 |
| Qdrant | 1.15.1参考镜像 | RAG和发布测试 |
| 用户文档 | PDF、DOCX；扫描件不保证隐式OCR | 解析、格式/签名和大小测试 |
| 面试复盘输入 | 文本；音频取决于配置的转写提供方 | 合成逐字稿、模拟转写和同意门禁 |
| FastAPI前端 | Vue生产Build由FastAPI静态提供 | Build和E2E |

版本权威仍是CI、Docker Compose、Dockerfile、Lockfile和可复现检查。本表只做快速
导航；升级任一主版本需更新来源、专项测试和本表。
