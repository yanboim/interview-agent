# Nginx网关

Compose部署通过Nginx暴露唯一公共HTTP入口：

```text
客户端 -> host:${GATEWAY_HTTP_PORT:-80} -> gateway:8080 -> app:8000
```

应用仍可由运维通过 `127.0.0.1:${APP_HOST_PORT:-8000}` 访问。PostgreSQL、Redis、
Qdrant、Prometheus和Grafana保持仅Loopback；OpenTelemetry Collector不发布宿主端口。

## 配置

默认值不合适时，在被忽略的生产 `.env` 中设置：

```dotenv
GATEWAY_BIND_ADDRESS=0.0.0.0
GATEWAY_HTTP_PORT=80
FORWARDED_ALLOW_IPS=*
```

只有应用端口保持Loopback且Compose网络可信时，`FORWARDED_ALLOW_IPS=*` 才安全。不得
把应用容器直接发布到公共接口。

网关：

- 转发原始Host、客户端地址和协议，并在公共边缘替换不可信入站 `X-Forwarded-For`；
- 支持连接Upgrade和无缓冲长响应；
- 允许最大32 MiB请求体；
- 上游连接超时5秒，响应超时5分钟；
- 公共 `/metrics` 返回404；
- Access Log不包含Query String；
- 使用镜像的非特权UID/GID 101、只读根文件系统、删除Capabilities并启用
  no-new-privileges。

## 部署

更新生产前验证：

```bash
docker compose config --quiet
docker run --rm \
  -v "$PWD/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  nginx:1.28.0-alpine nginx -t
make harness-check
```

启动或协调网关：

```bash
docker compose up -d gateway
docker compose ps gateway app
curl -fsS http://127.0.0.1:${GATEWAY_HTTP_PORT:-80}/health
curl -fsS http://127.0.0.1:${GATEWAY_HTTP_PORT:-80}/ready
```

宿主防火墙或云安全组允许配置TCP端口后，验证 `http://<server-ip>/` 可访问。

## TLS

明文HTTP只用于初始IP访问或可信上游负载均衡器。在不可信网络传输凭据前，配置域名和
可信证书、增加443监听、把HTTP重定向到HTTPS，并只在证书验证后启用HSTS。不得为图
方便而通过此网关暴露Grafana或其他基础设施服务。

## 回滚

只移除网关服务：

```bash
docker compose stop gateway
docker compose rm gateway
```

应用仍可通过本地Loopback运维端口访问。不得删除命名卷。
