"""面试答题幂等领取与重放的测试。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.application.interview_service import (
    InterviewAnswerConflict,
    InterviewAnswerService,
)
from app.database import interview_answer_attempts, interview_turns
from app.storage import ConversationStore


def assessment() -> dict[str, object]:
    return {
        "overall": 8.0,
        "dimensions": {"accuracy": 8.0},
        "strengths": ["准确"],
        "weaknesses": ["可补充异常路径"],
        "feedback": "回答清晰。",
        "reference_answer": "说明事务边界与失败恢复。",
    }


def create_interview(store: ConversationStore, *, total_questions: int = 2) -> None:
    store.initialize()
    store.create_interview(
        user_id="user-1",
        interview_id="interview-1",
        topic="分布式系统",
        level="高级",
        total_questions=total_questions,
        first_question="如何保证幂等？",
    )


def test_completed_retry_returns_stored_response_without_model_calls(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "idempotency.db")
    create_interview(store)
    assessor = MagicMock(return_value=assessment())
    generator = MagicMock(return_value="如何处理并发竞争？")
    service = InterviewAnswerService(
        store,
        assessor=assessor,
        question_generator=generator,
        assessment_prompt_version="assessment-prompt-test",
        assessment_schema_version="assessment-schema-test",
        model_version="model-test",
    )

    first = service.submit(
        user_id="user-1",
        interview_id="interview-1",
        answer="使用唯一请求键和条件更新。",
        idempotency_key="answer-key-1",
    )
    replay = service.submit(
        user_id="user-1",
        interview_id="interview-1",
        answer="使用唯一请求键和条件更新。",
        idempotency_key="answer-key-1",
    )

    assert replay == first
    assessor.assert_called_once()
    generator.assert_called_once()
    assert len(
        store.get_interview_answer_attempts(
            user_id="user-1",
            interview_id="interview-1",
        )
    ) == 1
    assert len(
        store.get_interview_turns(
            user_id="user-1",
            interview_id="interview-1",
        )
    ) == 2
    with store.engine.connect() as connection:
        turn = connection.execute(
            select(interview_turns).where(interview_turns.c.turn_index == 1)
        ).mappings().one()
        attempt = connection.execute(select(interview_answer_attempts)).mappings().one()
    assert turn["assessment_prompt_version"] == "assessment-prompt-test"
    assert turn["assessment_schema_version"] == "assessment-schema-test"
    assert turn["assessment_model_version"] == "model-test"
    assert attempt["prompt_version"] == "assessment-prompt-test"
    assert attempt["schema_version"] == "assessment-schema-test"
    assert attempt["model_version"] == "model-test"


@pytest.mark.parametrize("second_key", ["answer-key-1", "answer-key-2"])
def test_concurrent_submission_runs_models_once(tmp_path, second_key) -> None:
    database = tmp_path / f"concurrent-{second_key}.db"
    first_store = ConversationStore(database)
    second_store = ConversationStore(database)
    create_interview(first_store)
    second_store.initialize()
    scoring_started = Event()
    release_scoring = Event()

    def blocking_assessment(**_kwargs):
        scoring_started.set()
        assert release_scoring.wait(timeout=5)
        return assessment()

    assessor = MagicMock(side_effect=blocking_assessment)
    generator = MagicMock(return_value="下一题")
    first_service = InterviewAnswerService(
        first_store,
        assessor=assessor,
        question_generator=generator,
    )
    second_service = InterviewAnswerService(
        second_store,
        assessor=assessor,
        question_generator=generator,
    )
    submit_args = {
        "user_id": "user-1",
        "interview_id": "interview-1",
        "answer": "通过数据库条件更新领取回合。",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(
            first_service.submit,
            **submit_args,
            idempotency_key="answer-key-1",
        )
        assert scoring_started.wait(timeout=5)
        with pytest.raises(InterviewAnswerConflict):
            second_service.submit(
                **submit_args,
                idempotency_key=second_key,
            )
        release_scoring.set()
        assert winner.result(timeout=5)["status"] == "active"

    assessor.assert_called_once()
    generator.assert_called_once()
    with first_store.engine.connect() as connection:
        attempts = connection.execute(
            select(func.count()).select_from(interview_answer_attempts)
        ).scalar_one()
        turns = connection.execute(
            select(func.count()).select_from(interview_turns)
        ).scalar_one()
    assert attempts == 1
    assert turns == 2


def test_reusing_completed_key_with_different_answer_is_rejected(tmp_path) -> None:
    store = ConversationStore(tmp_path / "key-reuse.db")
    create_interview(store, total_questions=1)
    assessor = MagicMock(return_value=assessment())
    service = InterviewAnswerService(
        store,
        assessor=assessor,
        question_generator=MagicMock(),
    )
    service.submit(
        user_id="user-1",
        interview_id="interview-1",
        answer="原始回答",
        idempotency_key="answer-key-1",
    )

    with pytest.raises(InterviewAnswerConflict, match="不能用于不同回答"):
        service.submit(
            user_id="user-1",
            interview_id="interview-1",
            answer="修改后的回答",
            idempotency_key="answer-key-1",
        )
    assessor.assert_called_once()


def test_handled_model_failure_can_retry_same_command(tmp_path) -> None:
    store = ConversationStore(tmp_path / "failure.db")
    create_interview(store, total_questions=1)
    assessor = MagicMock(
        side_effect=[RuntimeError("provider unavailable"), assessment()]
    )
    service = InterviewAnswerService(
        store,
        assessor=assessor,
        question_generator=MagicMock(),
    )
    command = {
        "user_id": "user-1",
        "interview_id": "interview-1",
        "answer": "使用事务状态机。",
        "idempotency_key": "answer-key-1",
    }

    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.submit(**command)
    result = service.submit(**command)

    assert result["status"] == "completed"
    assert assessor.call_count == 2
    with store.engine.connect() as connection:
        row = connection.execute(select(interview_turns)).mappings().one()
    assert row["submission_status"] == "completed"
    assert row["submission_error"] is None
    assert row["result_json"]


def test_stale_claim_token_cannot_commit(tmp_path) -> None:
    store = ConversationStore(tmp_path / "claim-token.db")
    create_interview(store, total_questions=1)
    claim = store.claim_interview_answer(
        user_id="user-1",
        interview_id="interview-1",
        idempotency_key="answer-key-1",
        answer_digest="digest",
        claim_token="owner-token",
    )

    with pytest.raises(ValueError, match="claim lost"):
        store.complete_interview_answer(
            turn_id=int(dict(claim["turn"])["id"]),  # type: ignore[arg-type]
            claim_token="stale-token",
            user_id="user-1",
            interview_id="interview-1",
            turn_index=1,
            answer="回答",
            score=8,
            feedback="反馈",
            dimensions_json="{}",
            strengths_json="[]",
            weaknesses_json="[]",
            reference_answer=None,
            next_question=None,
            response={"status": "completed"},
        )
