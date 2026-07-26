import hashlib
import json
import logging
from typing import Any, Callable, Protocol
from uuid import uuid4


logger = logging.getLogger(__name__)


class InterviewAnswerRepository(Protocol):
    def claim_interview_answer(self, **kwargs: Any) -> dict[str, object]: ...

    def fail_interview_answer(self, **kwargs: Any) -> bool: ...

    def complete_interview_answer(self, **kwargs: Any) -> str: ...


class InterviewAnswerError(RuntimeError):
    """Base application error for initial answer submission."""


class InterviewAnswerNotFound(InterviewAnswerError):
    pass


class InterviewAnswerConflict(InterviewAnswerError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class InterviewAnswerService:
    def __init__(
        self,
        repository: InterviewAnswerRepository,
        *,
        assessor: Callable[..., dict[str, Any]],
        question_generator: Callable[..., str],
    ) -> None:
        self.repository = repository
        self.assessor = assessor
        self.question_generator = question_generator

    def submit(
        self,
        *,
        user_id: str,
        interview_id: str,
        answer: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        answer_digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()
        claim_token = str(uuid4())
        claim = self.repository.claim_interview_answer(
            user_id=user_id,
            interview_id=interview_id,
            idempotency_key=idempotency_key,
            answer_digest=answer_digest,
            claim_token=claim_token,
        )
        outcome = str(claim["outcome"])
        if outcome == "completed":
            return dict(claim["result"])  # type: ignore[arg-type]
        if outcome == "not_found":
            raise InterviewAnswerNotFound("模拟面试不存在")
        if outcome == "archived":
            raise InterviewAnswerConflict("该面试已归档")
        if outcome == "no_pending":
            raise InterviewAnswerConflict("没有待回答的问题")
        if outcome == "key_reused":
            raise InterviewAnswerConflict(
                "同一 Idempotency-Key 不能用于不同回答"
            )
        if outcome == "in_progress":
            raise InterviewAnswerConflict(
                "该回答正在评分，请稍后使用相同 Idempotency-Key 重试",
                retryable=True,
            )
        if outcome == "conflict":
            raise InterviewAnswerConflict("当前问题已被另一个回答请求领取")
        if outcome != "claimed":
            raise InterviewAnswerError(f"未知回答领取状态：{outcome}")

        interview = dict(claim["interview"])  # type: ignore[arg-type]
        turn = dict(claim["turn"])  # type: ignore[arg-type]
        turns = [
            dict(item)
            for item in claim["turns"]  # type: ignore[union-attr]
        ]
        turn_id = int(turn["id"])
        turn_index = int(turn["turn_index"])

        try:
            assessment = self.assessor(
                topic=str(interview["topic"]),
                level=str(interview["level"]),
                question=str(turn["question"]),
                answer=answer,
            )
            next_question = None
            if turn_index < int(interview["total_questions"]):
                completed_turns = [
                    item
                    for item in turns
                    if int(item["turn_index"]) < turn_index
                ]
                completed_turns.append({**turn, "answer": answer})
                next_question = self.question_generator(
                    topic=str(interview["topic"]),
                    level=str(interview["level"]),
                    turn_index=turn_index + 1,
                    previous_turns=completed_turns,
                )

            status = "active" if next_question else "completed"
            response: dict[str, object] = {
                "interview_id": interview_id,
                "turn_index": turn_index,
                "score": assessment["overall"],
                "dimensions": assessment["dimensions"],
                "strengths": assessment["strengths"],
                "weaknesses": assessment["weaknesses"],
                "feedback": assessment["feedback"],
                "reference_answer": assessment["reference_answer"],
                "next_question": next_question,
                "status": status,
            }
            committed_status = self.repository.complete_interview_answer(
                turn_id=turn_id,
                claim_token=claim_token,
                user_id=user_id,
                interview_id=interview_id,
                turn_index=turn_index,
                answer=answer,
                score=float(assessment["overall"]),
                feedback=str(assessment["feedback"]),
                dimensions_json=json.dumps(
                    assessment["dimensions"],
                    ensure_ascii=False,
                ),
                strengths_json=json.dumps(
                    assessment["strengths"],
                    ensure_ascii=False,
                ),
                weaknesses_json=json.dumps(
                    assessment["weaknesses"],
                    ensure_ascii=False,
                ),
                reference_answer=str(assessment["reference_answer"]),
                next_question=next_question,
                response=response,
            )
            if committed_status != status:
                raise InterviewAnswerError(
                    "面试提交状态与持久化状态不一致"
                )
            return response
        except Exception as exc:
            try:
                self.repository.fail_interview_answer(
                    turn_id=turn_id,
                    claim_token=claim_token,
                    error=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                logger.exception("标记面试回答失败状态时发生错误")
            raise
