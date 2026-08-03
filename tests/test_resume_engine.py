"""简历解析与事实受控优化稿引擎的测试。"""

from types import SimpleNamespace

from app.config import Settings
from app.resume_engine import analyze_resume


def test_resume_analysis_uses_background_timeout_policy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def invoke(self, _messages):
            return SimpleNamespace(
                content=(
                    '{"scores":{"match":80,"completeness":80,'
                    '"relevance":80,"clarity":80,"impact":80,"ats":80},'
                    '"keyword_matches":[],"keyword_gaps":[],"issues":[],'
                    '"draft":{"name":"","headline":"","summary":"",'
                    '"sections":[],"pending_questions":[]}}'
                )
            )

    def fake_create_chat_model(purpose: str, **kwargs):
        captured["purpose"] = purpose
        captured.update(kwargs)
        return FakeModel()

    monkeypatch.setattr(
        "app.resume_engine.create_chat_model",
        fake_create_chat_model,
    )
    settings = Settings(
        _env_file=None,
        zhipu_api_key="test-key",
        llm_timeout_seconds=45,
        llm_max_retries=2,
        resume_analysis_timeout_seconds=180,
        resume_analysis_max_retries=0,
    )

    analyze_resume(
        resume_text="Python backend engineer with measurable delivery.",
        job_description="Backend engineer",
        target_role="Backend engineer",
        experience_level="Senior",
        settings=settings,
    )

    assert captured["purpose"] == "resume_analysis"
    assert captured["timeout_seconds"] == 180
    assert captured["max_retries"] == 0
