"""模拟面试应用服务：保持模型调用在事务外，并以领取令牌封闭回答状态转换。"""

import hashlib
import json
import logging
from typing import Any, Callable, Protocol
from uuid import uuid4

from app.resume_interview import build_resume_interview_context


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


class InterviewStartError(RuntimeError):
    pass


class InterviewSourceNotFound(InterviewStartError):
    pass


class InterviewSourceConflict(InterviewStartError):
    pass


class InterviewStartService:
    def __init__(
        self,
        repository: Any,
        *,
        question_generator: Callable[..., str],
        prompt_version: str = "resume-interview-v1",
        schema_version: str = "question-text-v1",
        model_version: str = "",
    ) -> None:
        self.repository = repository
        self.question_generator = question_generator
        self.prompt_version = prompt_version
        self.schema_version = schema_version
        self.model_version = model_version

    def start(
        self,
        *,
        user_id: str,
        topic: str,
        level: str,
        question_count: int,
        resume_analysis_id: str | None = None,
    ) -> dict[str, object]:
        interview_id = str(uuid4())
        context = None
        source_resume_id = None
        source_display_name = None
        if resume_analysis_id:
            analysis = self.repository.get_resume_analysis(
                user_id=user_id,
                analysis_id=resume_analysis_id,
            )
            if not analysis:
                raise InterviewSourceNotFound("简历评估不存在")
            if analysis.get("status") != "ready":
                raise InterviewSourceConflict("只能使用已完成的简历评估")
            context = build_resume_interview_context(analysis)
            source_resume_id = str(analysis["resume_id"])
            source_display_name = str(
                analysis.get("original_filename") or "来源简历"
            )
            question = self.question_generator(
                topic=topic,
                level=level,
                turn_index=1,
                previous_turns=[],
                resume_context=context.model_dump(),
            )
        else:
            question = self.question_generator(
                topic=topic,
                level=level,
                turn_index=1,
                previous_turns=[],
            )
        self.repository.create_interview(
            user_id=user_id,
            interview_id=interview_id,
            topic=topic,
            level=level,
            total_questions=question_count,
            first_question=question,
            source_type="resume" if context else "general",
            source_resume_id=source_resume_id,
            source_analysis_id=resume_analysis_id,
            source_display_name=source_display_name,
            resume_context_json=(
                context.model_dump_json() if context else None
            ),
            question_prompt_version=self.prompt_version,
            question_schema_version=self.schema_version,
            question_model_version=self.model_version,
        )
        result: dict[str, object] = {
            "interview_id": interview_id,
            "topic": topic,
            "level": level,
            "question_count": question_count,
            "turn_index": 1,
            "question": question,
            "status": "active",
            "source_type": "resume" if context else "general",
        }
        if context:
            result["source_resume"] = {
                "resume_id": source_resume_id,
                "analysis_id": resume_analysis_id,
                "display_name": source_display_name,
                "available": True,
            }
        return result


class InterviewAnswerService:
    def __init__(
        self,
        repository: InterviewAnswerRepository,
        *,
        assessor: Callable[..., dict[str, Any]],
        question_generator: Callable[..., str],
        assessment_prompt_version: str = "interview-assessment-v1",
        assessment_schema_version: str = "assessment-v1",
        model_version: str = "",
    ) -> None:
        self.repository = repository
        self.assessor = assessor
        self.question_generator = question_generator
        self.assessment_prompt_version = assessment_prompt_version
        self.assessment_schema_version = assessment_schema_version
        self.model_version = model_version

    def submit(
        self,
        *,
        user_id: str,
        interview_id: str,
        answer: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        # 幂等键只允许重放同一回答；摘要避免用原文参与并发比较或日志记录。
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

        # 评分和出题可能访问外部模型，必须在 Repository 的短事务之外执行。
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
                generator_args: dict[str, Any] = {
                    "topic": str(interview["topic"]),
                    "level": str(interview["level"]),
                    "turn_index": turn_index + 1,
                    "previous_turns": completed_turns,
                }
                context_json = interview.get("resume_context_json")
                if context_json:
                    generator_args["resume_context"] = json.loads(
                        str(context_json)
                    )
                next_question = self.question_generator(**generator_args)

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
            # claim_token 是 owner fencing：迟到的旧请求不能覆盖新所有者的结果。
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
                prompt_version=self.assessment_prompt_version,
                schema_version=self.assessment_schema_version,
                model_version=self.model_version,
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
