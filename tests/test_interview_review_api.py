import asyncio

import httpx

import app.main as main_module
from app.api.routers import interview_reviews as review_routes
from app.main import app


def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_review_feature_gate_and_idempotency_contract(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "review_feature_enabled", False)
    disabled = request(
        "POST",
        "/api/interview-reviews/text",
        json={"transcript": "面试官：问题\n\n候选人：回答"},
        headers={"Idempotency-Key": "review-key-1"},
    )
    assert disabled.status_code == 404

    operation = app.openapi()["paths"]["/api/interview-reviews/text"]["post"]
    header = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert header["required"] is True


def test_text_review_uses_server_resolved_owner(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "review_feature_enabled", True)
    captured = {}

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(review_routes, "run_sync", run_inline)

    def create_text(**kwargs):
        captured.update(kwargs)
        return {
            "review_id": "review-1",
            "input_type": "text",
            "status": "awaiting_confirmation",
        }

    monkeypatch.setattr(
        main_module.interview_review_service,
        "create_text",
        create_text,
    )
    response = request(
        "POST",
        "/api/interview-reviews/text",
        json={"transcript": "面试官：问题\n\n候选人：回答"},
        headers={"Idempotency-Key": "review-key-1"},
    )

    assert response.status_code == 201
    assert captured == {
        "user_id": "anonymous",
        "transcript": "面试官：问题\n\n候选人：回答",
        "idempotency_key": "review-key-1",
    }


def test_review_list_and_delete_are_owner_scoped(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "review_feature_enabled", True)
    captured = []

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(review_routes, "run_sync", run_inline)
    monkeypatch.setattr(
        main_module.interview_review_service,
        "list",
        lambda **kwargs: captured.append(("list", kwargs)) or [],
    )
    monkeypatch.setattr(
        main_module.interview_review_service,
        "delete",
        lambda **kwargs: captured.append(("delete", kwargs)) or True,
    )

    assert request("GET", "/api/interview-reviews").json() == []
    assert request(
        "DELETE",
        "/api/interview-reviews/review-1",
    ).json() == {"deleted": True}
    assert captured == [
        ("list", {"user_id": "anonymous"}),
        (
            "delete",
            {"user_id": "anonymous", "review_id": "review-1"},
        ),
    ]
