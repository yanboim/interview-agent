# Nginx gateway

The Compose deployment exposes one public HTTP entry point through Nginx:

```text
Client -> host:${GATEWAY_HTTP_PORT:-80} -> gateway:8080 -> app:8000
```

The application remains available to operators at
`127.0.0.1:${APP_HOST_PORT:-8000}`. PostgreSQL, Redis, Qdrant, Prometheus, and
Grafana remain loopback-only; the OpenTelemetry collector has no published
host port.

## Configuration

Set these values in the ignored production `.env` when defaults are unsuitable:

```dotenv
GATEWAY_BIND_ADDRESS=0.0.0.0
GATEWAY_HTTP_PORT=80
FORWARDED_ALLOW_IPS=*
```

`FORWARDED_ALLOW_IPS=*` is safe only while the application port remains
loopback-only and the Compose network is trusted. Do not publish the
application container directly on a public interface.

The gateway:

- forwards the original host, client address, and protocol while replacing
  untrusted inbound `X-Forwarded-For` values at the public edge;
- supports connection upgrades and unbuffered long-running responses;
- allows request bodies up to 32 MiB;
- uses a five-second upstream connection timeout and a five-minute response
  timeout;
- returns 404 for public `/metrics`;
- emits access logs without query strings;
- runs as the image's unprivileged UID/GID 101 with a read-only root
  filesystem, dropped capabilities, and no-new-privileges.

## Deployment

Validate before updating production:

```bash
docker compose config --quiet
docker run --rm \
  -v "$PWD/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  nginx:1.28.0-alpine nginx -t
make harness-check
```

Start or reconcile the gateway:

```bash
docker compose up -d gateway
docker compose ps gateway app
curl -fsS http://127.0.0.1:${GATEWAY_HTTP_PORT:-80}/health
curl -fsS http://127.0.0.1:${GATEWAY_HTTP_PORT:-80}/ready
```

Verify that `http://<server-ip>/` is reachable after the host firewall or cloud
security group allows the configured TCP port.

## TLS

Plain HTTP is intended only for initial IP-based access or a trusted upstream
load balancer. Before sending credentials over an untrusted network, configure
a domain and trusted certificate, add a 443 listener, redirect HTTP to HTTPS,
and enable HSTS only after certificate validation. Do not expose Grafana or
other infrastructure services through this gateway as a shortcut.

## Rollback

Remove only the gateway service:

```bash
docker compose stop gateway
docker compose rm gateway
```

The application remains reachable locally through its loopback operator port.
Do not remove named volumes.
