"""简历 API 的集成测试。"""

import asyncio

import httpx

import app.main as main_module
from app.api.routers import resumes as resume_routes
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


def test_resume_upload_requires_feature_and_idempotency(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "resume_feature_enabled", False)
    disabled = request(
        "POST",
        "/api/resumes",
        files={"file": ("resume.pdf", b"%PDF-test", "application/pdf")},
        headers={"Idempotency-Key": "resume-key-1"},
    )
    assert disabled.status_code == 404

    operation = app.openapi()["paths"]["/api/resumes"]["post"]
    header = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert header["required"] is True


def test_resume_upload_uses_server_resolved_owner(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "resume_feature_enabled", True)
    captured = {}

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(resume_routes, "run_sync", run_inline)

    def create(**kwargs):
        captured.update(kwargs)
        return {
            "resume_id": "resume-1",
            "status": "uploaded",
            "analyses": [],
        }

    monkeypatch.setattr(main_module.resume_service, "create", create)
    response = request(
        "POST",
        "/api/resumes",
        files={
            "file": (
                "resume.docx",
                b"fake-docx-for-adapter-test",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )
        },
        data={"job_description": "Python工程师"},
        headers={"Idempotency-Key": "resume-key-1"},
    )

    assert response.status_code == 202
    assert response.json()["resume_id"] == "resume-1"
    assert captured["user_id"] == "anonymous"
    assert captured["original_filename"] == "resume.docx"
    assert captured["job_description"] == "Python工程师"
    assert captured["idempotency_key"] == "resume-key-1"


def test_resume_list_and_delete_are_owner_scoped(monkeypatch) -> None:
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "resume_feature_enabled", True)
    captured = []

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(resume_routes, "run_sync", run_inline)

    def list_resumes(**kwargs):
        captured.append(("list", kwargs))
        return []

    def delete_resume(**kwargs):
        captured.append(("delete", kwargs))
        return True

    monkeypatch.setattr(main_module.resume_service, "list", list_resumes)
    monkeypatch.setattr(main_module.resume_service, "delete", delete_resume)

    assert request("GET", "/api/resumes").json() == []
    deleted = request("DELETE", "/api/resumes/resume-1")
    assert deleted.json() == {"deleted": True}
    assert captured == [
        ("list", {"user_id": "anonymous"}),
        (
            "delete",
            {"user_id": "anonymous", "resume_id": "resume-1"},
        ),
    ]
