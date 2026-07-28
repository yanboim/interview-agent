"""Sanitized system-resource inventory for the administrator control plane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Callable, Literal
from urllib.parse import urlsplit

import httpx

from app.config import Settings


ResourceStatus = Literal[
    "healthy",
    "unavailable",
    "configured",
    "disabled",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    resource_id: str
    name: str
    category: str
    exposure: str
    description: str
    runbook: str
    critical: bool = False
    enabled: bool = True
    check: Callable[[], object] | None = None
    status_without_probe: ResourceStatus = "unknown"
    console_url: str = ""


def _safe_console_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return None
    return value


def _http_probe(url: str, timeout_seconds: float) -> Callable[[], None] | None:
    if not url:
        return None

    def check() -> None:
        with httpx.Client(
            timeout=max(0.1, timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(
                url,
                headers={"User-Agent": "interview-agent-resource-probe/1"},
            )
            response.raise_for_status()

    return check


class SystemResourceCenter:
    def __init__(self, resources: list[ResourceSpec]) -> None:
        self._resources = tuple(resources)

    def snapshot(self) -> dict[str, object]:
        items = [self._inspect(resource) for resource in self._resources]
        summary = {
            status: sum(item["status"] == status for item in items)
            for status in (
                "healthy",
                "unavailable",
                "configured",
                "disabled",
                "unknown",
            )
        }
        required_unavailable = any(
            item["critical"] and item["status"] == "unavailable"
            for item in items
        )
        return {
            "overall_status": (
                "degraded" if required_unavailable else "healthy"
            ),
            "checked_at": datetime.now(UTC).isoformat(),
            "summary": summary,
            "resources": items,
        }

    @staticmethod
    def _inspect(resource: ResourceSpec) -> dict[str, object]:
        latency_ms: int | None = None
        if not resource.enabled:
            status: ResourceStatus = "disabled"
            detail = "未启用"
        elif resource.check is None:
            status = resource.status_without_probe
            detail = (
                "已配置，未提供实时探针"
                if status == "configured"
                else "未配置实时探针"
            )
        else:
            started_at = time.monotonic()
            try:
                resource.check()
                status = "healthy"
                detail = "实时检查正常"
            except Exception:
                status = "unavailable"
                detail = "实时检查失败，请查看对应运行手册"
            latency_ms = max(
                0, round((time.monotonic() - started_at) * 1000)
            )

        return {
            "id": resource.resource_id,
            "name": resource.name,
            "category": resource.category,
            "status": status,
            "detail": detail,
            "exposure": resource.exposure,
            "critical": resource.critical,
            "description": resource.description,
            "runbook": resource.runbook,
            "latency_ms": latency_ms,
            "console_url": _safe_console_url(resource.console_url),
        }


def create_system_resource_center(
    settings: Settings,
    *,
    database_check: Callable[[], object],
    redis_check: Callable[[], object],
    redis_enabled: bool,
    worker_check: Callable[[], object],
    qdrant_check: Callable[[], object],
) -> SystemResourceCenter:
    timeout = settings.resource_probe_timeout_seconds
    database_name = (
        "PostgreSQL"
        if settings.database_url.startswith(("postgresql:", "postgres:"))
        else "SQLite"
    )
    resources = [
        ResourceSpec(
            "gateway",
            "Nginx 网关",
            "edge",
            "public_gateway",
            "统一 HTTP 入口、代理头与基础流量边界。",
            "docs/reliability/nginx-gateway.md",
            critical=True,
            check=_http_probe(settings.resource_gateway_health_url, timeout),
        ),
        ResourceSpec(
            "app",
            "应用服务",
            "application",
            "loopback",
            "FastAPI API、管理后台和前端静态资源。",
            "docs/operations/TROUBLESHOOTING.md",
            critical=True,
            check=lambda: None,
        ),
        ResourceSpec(
            "worker",
            "后台 Worker",
            "jobs",
            "private_network",
            "消费知识导入等持久化后台任务。",
            "docs/reliability/README.md",
            enabled=redis_enabled,
            check=worker_check if redis_enabled else None,
        ),
        ResourceSpec(
            "database",
            database_name,
            "data",
            "loopback",
            "保存账号、会话、面试、学习和审计记录。",
            "docs/operations/BACKUP-RESTORE.md",
            critical=True,
            check=database_check,
        ),
        ResourceSpec(
            "redis",
            "Redis",
            "data",
            "loopback",
            "共享限流、缓存和持久化任务队列。",
            "docs/reliability/README.md",
            critical=True,
            enabled=redis_enabled,
            check=redis_check if redis_enabled else None,
        ),
        ResourceSpec(
            "qdrant",
            "Qdrant",
            "data",
            "loopback",
            "保存版本化私有知识索引。",
            "docs/reliability/README.md",
            critical=True,
            check=qdrant_check,
        ),
        ResourceSpec(
            "prometheus",
            "Prometheus",
            "observability",
            "loopback",
            "采集应用指标和告警规则。",
            "docs/operations/OBSERVABILITY.md",
            check=_http_probe(settings.resource_prometheus_health_url, timeout),
        ),
        ResourceSpec(
            "grafana",
            "Grafana",
            "observability",
            "loopback",
            "提供经过独立运维认证的指标仪表盘。",
            "docs/operations/OBSERVABILITY.md",
            check=_http_probe(settings.resource_grafana_health_url, timeout),
            console_url=settings.admin_grafana_url,
        ),
        ResourceSpec(
            "otel",
            "OpenTelemetry Collector",
            "observability",
            "private_network",
            "接收并导出应用追踪数据。",
            "docs/operations/OBSERVABILITY.md",
            enabled=settings.otel_enabled,
            status_without_probe="configured",
        ),
    ]
    return SystemResourceCenter(resources)
