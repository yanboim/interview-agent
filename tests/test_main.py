import asyncio
from types import SimpleNamespace

import httpx

import app.main as main_module
from app.main import app, extract_message_text, main_web_app, web_app


def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_health() -> None:
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_app() -> None:
    response = asyncio.run(web_app())
    assert response.status_code == 200
    # 新前端为 Vue SPA,入口 index.html 含应用根节点与标题。
    assert "Interview Lab" in response.path.read_text(encoding="utf-8")


def test_spa_deep_links_return_frontend_shell() -> None:
    response = asyncio.run(main_web_app())
    assert response.status_code == 200
    assert "Interview Lab" in response.path.read_text(encoding="utf-8")


def test_chat_rejects_blank_values() -> None:
    response = request(
        "POST",
        "/api/chat",
        json={"session_id": "  ", "message": "hi"},
    )
    assert response.status_code == 422


def test_chat_endpoints_require_idempotency_key() -> None:
    paths = app.openapi()["paths"]
    for path in ("/api/chat", "/api/chat/stream"):
        header = next(
            parameter
            for parameter in paths[path]["post"]["parameters"]
            if parameter["name"] == "Idempotency-Key"
        )
        assert header["required"] is True


def test_extract_message_text_supports_content_blocks() -> None:
    message = SimpleNamespace(content=[{"type": "text", "text": "第一段"}, "第二段"])
    assert extract_message_text(message) == "第一段\n第二段"


def test_interview_answer_requires_and_forwards_idempotency_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    operation = app.openapi()["paths"][
        "/api/interviews/{interview_id}/answer"
    ]["post"]
    header = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert header["required"] is True

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        main_module.interview_answer_service,
        "submit",
        lambda **kwargs: {
            "interview_id": kwargs["interview_id"],
            "idempotency_key": kwargs["idempotency_key"],
        },
    )
    accepted = asyncio.run(
        main_module.answer_interview(
            "interview-1",
            main_module.InterviewAnswerRequest(
                user_id="user-1",
                answer="回答",
            ),
            SimpleNamespace(state=SimpleNamespace()),
            idempotency_key="answer-key-1",
        )
    )

    assert accepted["idempotency_key"] == "answer-key-1"
