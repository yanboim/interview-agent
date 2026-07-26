import asyncio
from types import SimpleNamespace

import httpx

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


def test_extract_message_text_supports_content_blocks() -> None:
    message = SimpleNamespace(content=[{"type": "text", "text": "第一段"}, "第二段"])
    assert extract_message_text(message) == "第一段\n第二段"
