"""系统资源中心（依赖探测、Worker 心跳）的测试。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers import admin as admin_routes
from app.auth import AuthenticatedUser
from app.config import Settings
from app.system_resources import (
    ResourceSpec,
    SystemResourceCenter,
    operator_console_links,
)


def request_for(role: str = "admin"):
    return SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id=f"{role}-1",
                username=role,
                role=role,
            )
        )
    )


def test_resource_snapshot_redacts_probe_errors_and_unsafe_links() -> None:
    def failed_probe() -> None:
        raise RuntimeError(
            "postgresql://operator:secret-password@private-db/resource"
        )

    center = SystemResourceCenter(
        [
            ResourceSpec(
                "app",
                "App",
                "application",
                "loopback",
                "Application",
                "docs/reliability/README.md",
                critical=True,
                check=lambda: None,
            ),
            ResourceSpec(
                "database",
                "Database",
                "data",
                "private_network",
                "Database",
                "docs/operations/BACKUP-RESTORE.md",
                critical=True,
                check=failed_probe,
                console_url="http://admin:password@private-db/",
            ),
        ]
    )

    snapshot = center.snapshot()
    serialized = json.dumps(snapshot)

    assert snapshot["overall_status"] == "degraded"
    assert snapshot["summary"]["healthy"] == 1
    assert snapshot["summary"]["unavailable"] == 1
    assert "secret-password" not in serialized
    assert "private-db" not in serialized
    assert snapshot["resources"][1]["console_url"] is None


def test_operator_console_links_keep_only_safe_configured_urls() -> None:
    settings = Settings(
        _env_file=None,
        admin_prometheus_url="https://ops.example.test/prometheus/",
        admin_grafana_url="https://admin:secret@ops.example.test/grafana/",
    )

    assert operator_console_links(settings) == [
        {
            "id": "prometheus",
            "name": "Prometheus",
            "url": "https://ops.example.test/prometheus/",
        }
    ]


def test_admin_runtime_projects_safe_operator_console_links(monkeypatch) -> None:
    runtime = SimpleNamespace(
        settings=Settings(
            _env_file=None,
            admin_prometheus_url="https://ops.example.test/prometheus/",
            admin_grafana_url="https://ops.example.test/grafana/",
        ),
        conversation_store=SimpleNamespace(check_connection=lambda: None),
        redis_runtime=SimpleNamespace(check=lambda: None),
        require_serving_knowledge=lambda: None,
    )
    monkeypatch.setattr(admin_routes, "get_runtime", lambda: runtime)

    async def direct_run(function):
        return function()

    monkeypatch.setattr(admin_routes, "run_sync", direct_run)

    payload = asyncio.run(admin_routes.admin_runtime(request_for()))

    assert payload["operator_links"] == [
        {
            "id": "prometheus",
            "name": "Prometheus",
            "url": "https://ops.example.test/prometheus/",
        },
        {
            "id": "grafana",
            "name": "Grafana",
            "url": "https://ops.example.test/grafana/",
        },
    ]


def test_resource_snapshot_distinguishes_unknown_and_disabled() -> None:
    center = SystemResourceCenter(
        [
            ResourceSpec(
                "worker",
                "Worker",
                "jobs",
                "private_network",
                "Worker",
                "docs/reliability/README.md",
            ),
            ResourceSpec(
                "otel",
                "OTel",
                "observability",
                "private_network",
                "OTel",
                "docs/operations/OBSERVABILITY.md",
                enabled=False,
                status_without_probe="configured",
            ),
        ]
    )

    snapshot = center.snapshot()

    assert [item["status"] for item in snapshot["resources"]] == [
        "unknown",
        "disabled",
    ]


def test_resource_snapshot_reports_worker_heartbeat_failure() -> None:
    def stale_worker() -> None:
        raise RuntimeError(
            '{"instance_id":"private-worker","heartbeat_at":0}'
        )

    center = SystemResourceCenter(
        [
            ResourceSpec(
                "worker",
                "Worker",
                "jobs",
                "private_network",
                "Worker",
                "docs/reliability/README.md",
                check=stale_worker,
            )
        ]
    )

    snapshot = center.snapshot()
    serialized = json.dumps(snapshot)

    assert snapshot["resources"][0]["status"] == "unavailable"
    assert "private-worker" not in serialized


def test_admin_resource_endpoint_requires_admin_and_returns_snapshot(
    monkeypatch,
) -> None:
    center = SystemResourceCenter(
        [
            ResourceSpec(
                "app",
                "App",
                "application",
                "loopback",
                "Application",
                "docs/reliability/README.md",
                check=lambda: None,
            )
        ]
    )
    monkeypatch.setattr(
        admin_routes,
        "get_runtime",
        lambda: SimpleNamespace(system_resource_center=center),
    )
    async def direct_run(function):
        return function()

    monkeypatch.setattr(admin_routes, "run_sync", direct_run)

    payload = asyncio.run(admin_routes.admin_resources(request_for()))

    assert payload["operator"] == "admin"
    assert payload["resources"][0]["status"] == "healthy"

    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_routes.admin_resources(request_for("user")))
    assert error.value.status_code == 403
