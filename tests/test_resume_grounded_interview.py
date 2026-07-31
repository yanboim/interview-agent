import json
from pathlib import Path

import pytest

from app.application.interview_service import (
    InterviewAnswerService,
    InterviewSourceConflict,
    InterviewSourceNotFound,
    InterviewStartService,
)
from app.storage import ConversationStore


def ready_analysis(store: ConversationStore, *, user_id: str = "user-1") -> str:
    resume_id = "resume-1"
    analysis_id = "analysis-1"
    store.create_resume_with_analysis(
        user_id=user_id,
        resume_id=resume_id,
        analysis_id=analysis_id,
        original_filename="synthetic.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        size_bytes=100,
        sha256="a" * 64,
        storage_key="owner/resume.docx",
        idempotency_key="resume-key",
        request_digest="b" * 64,
        job_description="需要 Python 和可观测性经验",
        target_role="后端工程师",
        experience_level="高级",
        prompt_version="resume-analysis-v1",
    )
    claimed = store.claim_resume_analysis(
        analysis_id=analysis_id,
        claim_token="claim-1",
    )
    assert claimed
    completed = store.complete_resume_analysis(
        analysis_id=analysis_id,
        claim_token="claim-1",
        parsed_text="候选人姓名不应进入面试上下文。5年 Python 经验。",
        report_json=json.dumps(
            {
                "scores": {"match": 80},
                "keyword_matches": ["Python"],
                "keyword_gaps": ["可观测性"],
                "issues": [
                    {
                        "evidence": "负责订单接口优化",
                        "suggestion": "说明技术权衡",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        draft_json=json.dumps(
            {
                "name": "张三",
                "headline": "高级后端工程师",
                "summary": "",
                "sections": [
                    {
                        "title": "项目经历",
                        "items": ["订单接口延迟降低30%"],
                    }
                ],
                "pending_questions": [],
            },
            ensure_ascii=False,
        ),
        warnings_json="[]",
        model_version="test-model",
    )
    assert completed
    return analysis_id


def test_resume_grounded_interview_uses_minimized_stable_snapshot(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path / "interview.db")
    analysis_id = ready_analysis(store)
    generated: list[dict[str, object]] = []

    def generator(**kwargs):
        generated.append(kwargs)
        return "请说明订单接口优化中的技术权衡。"

    start_service = InterviewStartService(
        store,
        question_generator=generator,
    )
    started = start_service.start(
        user_id="user-1",
        topic="后端工程",
        level="高级",
        question_count=2,
        resume_analysis_id=analysis_id,
    )

    context = generated[0]["resume_context"]
    assert context["keyword_gaps"] == ["可观测性"]
    assert "订单接口延迟降低30%" in context["evidence_claims"]
    assert "张三" not in json.dumps(context, ensure_ascii=False)
    assert started["source_type"] == "resume"

    answer_service = InterviewAnswerService(
        store,
        assessor=lambda **_: {
            "overall": 8,
            "dimensions": {},
            "strengths": [],
            "weaknesses": [],
            "feedback": "清晰",
            "reference_answer": "参考",
        },
        question_generator=generator,
    )
    answer_service.submit(
        user_id="user-1",
        interview_id=str(started["interview_id"]),
        answer="我会先建立延迟基线再验证。",
        idempotency_key="answer-key-1",
    )
    assert generated[1]["resume_context"] == context


def test_resume_source_is_owner_scoped_and_must_be_ready(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path / "interview.db")
    analysis_id = ready_analysis(store)
    service = InterviewStartService(
        store,
        question_generator=lambda **_: "问题",
    )

    with pytest.raises(InterviewSourceNotFound):
        service.start(
            user_id="user-2",
            topic="后端",
            level="高级",
            question_count=1,
            resume_analysis_id=analysis_id,
        )
    retry = store.create_resume_analysis(
        user_id="user-1",
        resume_id="resume-1",
        analysis_id="analysis-pending",
        idempotency_key="analysis-key",
        request_digest="c" * 64,
        job_description="Python",
        target_role="后端",
        experience_level="高级",
        prompt_version="v1",
    )
    assert retry["outcome"] == "created"
    with pytest.raises(InterviewSourceConflict):
        service.start(
            user_id="user-1",
            topic="后端",
            level="高级",
            question_count=1,
            resume_analysis_id="analysis-pending",
        )


def test_general_path_unchanged_and_deleted_source_history_survives(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path / "interview.db")
    analysis_id = ready_analysis(store)
    calls = []

    def generator(**kwargs):
        calls.append(kwargs)
        return "问题"

    service = InterviewStartService(store, question_generator=generator)
    general = service.start(
        user_id="user-1",
        topic="系统设计",
        level="高级",
        question_count=1,
    )
    assert "resume_context" not in calls[0]
    assert general["source_type"] == "general"

    grounded = service.start(
        user_id="user-1",
        topic="系统设计",
        level="高级",
        question_count=1,
        resume_analysis_id=analysis_id,
    )
    assert store.delete_resume(user_id="user-1", resume_id="resume-1")
    historical = store.get_interview(
        user_id="user-1",
        interview_id=str(grounded["interview_id"]),
    )
    assert historical
    assert historical["source_resume"]["available"] is False
    assert store.get_interview_turns(
        user_id="user-1",
        interview_id=str(grounded["interview_id"]),
    )
