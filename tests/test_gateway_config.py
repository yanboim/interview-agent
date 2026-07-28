from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy" / "nginx" / "nginx.conf").read_text(
    encoding="utf-8"
)


def test_gateway_is_the_only_public_compose_entrypoint() -> None:
    assert (
        '"${GATEWAY_BIND_ADDRESS:-0.0.0.0}:'
        '${GATEWAY_HTTP_PORT:-80}:8080"'
    ) in COMPOSE
    assert '"127.0.0.1:${APP_HOST_PORT:-8000}:8000"' in COMPOSE
    assert COMPOSE.count("${GATEWAY_BIND_ADDRESS:-0.0.0.0}") == 1
    assert "nginx:1.28.0-alpine@sha256:" in COMPOSE


def test_gateway_preserves_proxy_semantics_and_blocks_metrics() -> None:
    required = [
        "resolver 127.0.0.11 valid=10s ipv6=off;",
        "server app:8000 resolve;",
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_set_header Upgrade $http_upgrade;",
        "proxy_set_header Connection $connection_upgrade;",
        "proxy_buffering off;",
        "proxy_read_timeout 300s;",
        "client_max_body_size 32m;",
        "location = /metrics",
        "return 404;",
    ]
    missing = [directive for directive in required if directive not in NGINX]
    assert missing == []


def test_gateway_container_is_hardened() -> None:
    required = [
        'user: "101:101"',
        "read_only: true",
        'cap_drop: ["ALL"]',
        'security_opt: ["no-new-privileges:true"]',
        "/var/cache/nginx",
        "/var/run",
        "/tmp",
        "gateway-health",
    ]
    missing = [directive for directive in required if directive not in COMPOSE]
    assert missing == []
