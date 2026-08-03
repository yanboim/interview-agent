"""Agent 工作流（训练方案）API 的集成测试。"""

import asyncio

import httpx

import app.main as main_module
from app.api.routers import learning as learning_routes
from app.main import app


def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_training_program_api_requires_idempotency_and_forwards_owner(monkeypatch):
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    captured = {}

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(learning_routes, "run_sync", run_inline)

    def propose(**kwargs):
        captured.update(kwargs)
        return {
            "run_id": "run-1",
            "status": "awaiting_confirmation",
            "proposal": {"candidates": []},
            "steps": [],
        }

    monkeypatch.setattr(main_module.agent_run_service, "propose_training_program", propose)
    missing = request(
        "POST",
        "/api/agent-runs/training-program",
        json={"user_id": "user-a", "topic": "RAG"},
    )
    assert missing.status_code == 422
    response = request(
        "POST",
        "/api/agent-runs/training-program",
        json={"user_id": "user-a", "topic": "RAG"},
        headers={"Idempotency-Key": "program-1"},
    )
    assert response.status_code == 201
    assert captured == {
        "user_id": "user-a",
        "topic": "RAG",
        "idempotency_key": "program-1",
    }


def test_agent_run_inspect_confirm_cancel_and_retry_are_owner_scoped(monkeypatch):
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    calls = []

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(learning_routes, "run_sync", run_inline)
    for transition in ("confirm", "cancel", "retry"):
        monkeypatch.setattr(
            main_module.agent_run_service,
            transition,
            lambda _transition=transition, **kwargs: calls.append(
                (_transition, kwargs)
            ) or {"run_id": kwargs["run_id"], "status": "completed"},
        )
        response = request(
            "POST",
            f"/api/agent-runs/run-1/{transition}",
            json={"user_id": "user-a"},
        )
        assert response.status_code == 200
    assert calls == [
        ("confirm", {"user_id": "user-a", "run_id": "run-1"}),
        ("cancel", {"user_id": "user-a", "run_id": "run-1"}),
        ("retry", {"user_id": "user-a", "run_id": "run-1"}),
    ]


def test_agent_run_events_stream_safe_lifecycle_events(monkeypatch):
    monkeypatch.setattr(main_module.settings, "auth_required", False)

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(learning_routes, "run_sync", run_inline)
    monkeypatch.setattr(
        main_module.agent_run_service,
        "inspect",
        lambda **_kwargs: {
            "run_id": "run-1",
            "events": [
                {"event": "planned", "run_id": "run-1"},
                {"event": "done", "run_id": "run-1"},
            ],
        },
    )

    response = request(
        "GET", "/api/agent-runs/run-1/events?user_id=user-a"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: planned" in response.text
    assert "event: done" in response.text
    assert "reasoning" not in response.text
