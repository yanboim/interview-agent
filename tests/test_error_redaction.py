"""审计/可观测性细节脱敏的测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.api.routers import admin as admin_routes
from app.api.routers import interviews as interview_routes
from app.api.schemas import InterviewStartRequest
from app.auth import AuthenticatedUser


SECRET_EXCEPTION = (
    "provider=https://internal.example token=sk-test-secret-1234567890"
)


def _raise_secret(*_args, **_kwargs) -> None:
    raise RuntimeError(SECRET_EXCEPTION)


async def _run_inline(function, *args, **kwargs):
    return function(*args, **kwargs)


def test_readiness_does_not_return_dependency_exception_text(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module.conversation_store,
        "check_connection",
        _raise_secret,
    )
    monkeypatch.setattr(main_module, "run_sync", _run_inline)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(main_module.readiness())

    assert caught.value.status_code == 503
    assert caught.value.detail == "应用依赖暂时不可用，请稍后重试"
    assert SECRET_EXCEPTION not in str(caught.value.detail)


def test_interview_unknown_failure_returns_stable_public_message(
    monkeypatch,
) -> None:
    runtime = SimpleNamespace(
        interview_start_service=SimpleNamespace(start=_raise_secret)
    )
    monkeypatch.setattr(interview_routes, "get_runtime", lambda: runtime)
    monkeypatch.setattr(interview_routes, "run_sync", _run_inline)
    monkeypatch.setattr(main_module.settings, "auth_required", False)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            interview_routes.start_interview(
                InterviewStartRequest(
                    user_id="user-1",
                    topic="可靠性",
                    level="高级",
                    question_count=3,
                ),
                SimpleNamespace(state=SimpleNamespace()),
            )
        )

    assert caught.value.status_code == 500
    assert caught.value.detail == "模拟面试启动失败，请稍后重试"
    assert SECRET_EXCEPTION not in str(caught.value.detail)


def test_admin_dependency_summary_omits_exception_type_and_text(
    monkeypatch,
) -> None:
    failing = MagicMock(side_effect=RuntimeError(SECRET_EXCEPTION))
    runtime = SimpleNamespace(
        conversation_store=SimpleNamespace(check_connection=failing),
        redis_runtime=SimpleNamespace(check=failing),
        require_serving_knowledge=failing,
        settings=main_module.settings,
    )
    monkeypatch.setattr(admin_routes, "get_runtime", lambda: runtime)
    monkeypatch.setattr(admin_routes, "run_sync", _run_inline)
    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id="admin-1",
                username="operator",
                role="admin",
            )
        )
    )

    result = asyncio.run(admin_routes.admin_runtime(request))

    assert result["dependencies"] == {
        "database": {"status": "error", "detail": "连接检查失败"},
        "redis": {"status": "error", "detail": "连接检查失败"},
        "qdrant": {"status": "error", "detail": "连接检查失败"},
    }
    assert SECRET_EXCEPTION not in str(result)
    assert "RuntimeError" not in str(result)
