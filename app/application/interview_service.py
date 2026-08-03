"""模拟面试应用服务：保持模型调用在事务外，并以领取令牌封闭回答状态转换。"""

import hashlib
import json
import logging
from typing import Any, Callable, Protocol
from uuid import uuid4

from app.application.interview_capabilities import (
    AnswerEvaluationRequestV1,
    AnswerEvaluator,
    QuestionGenerationRequestV1,
    QuestionGenerator,
)
from app.resume_interview import build_resume_interview_context


logger = logging.getLogger(__name__)


class InterviewAnswerRepository(Protocol):
    """面试答案持久化的最小契约（结构子类型协议）。

    实际实现是 ``app.storage.ConversationStore``。用协议解耦，使应用
    服务可被注入测试替身，而不依赖具体 SQLAlchemy 适配器。
    """

    def claim_interview_answer(self, **kwargs: Any) -> dict[str, object]: ...

    def fail_interview_answer(self, **kwargs: Any) -> bool: ...

    def complete_interview_answer(self, **kwargs: Any) -> str: ...


class InterviewStartRepository(Protocol):
    def get_resume_analysis(self, **kwargs: Any) -> dict[str, object] | None: ...
    def create_interview(self, **kwargs: Any) -> None: ...


class InterviewAnswerError(RuntimeError):
    """面试答案提交的应用层基类错误。"""


class InterviewAnswerNotFound(InterviewAnswerError):
    pass


class InterviewAnswerConflict(InterviewAnswerError):
    """面试答案提交的并发/状态冲突。

    ``retryable`` 标记客户端是否可稍后用相同幂等键重试（如该回答仍在评分中）。
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class InterviewStartError(RuntimeError):
    """面试开始的应用层基类错误。"""


class InterviewSourceNotFound(InterviewStartError):
    pass


class InterviewSourceConflict(InterviewStartError):
    pass


class InterviewStartService:
    """创建模拟面试并生成首个问题。

    支持通用面试与基于简历评估的定向面试两种来源；模型出题发生在
    持久化之前，使首题与面试记录一起写入。
    """

    def __init__(
        self,
        repository: InterviewStartRepository,
        *,
        question_generator: Callable[..., str] | None = None,
        capabilities: QuestionGenerator | None = None,
        prompt_version: str = "resume-interview-v1",
        schema_version: str = "question-text-v1",
        model_version: str = "",
    ) -> None:
        """注入持久化仓库与出题回调。

        参数:
            repository: 持久化适配器，需提供简历评估读取与面试创建方法。
            question_generator: 模型出题回调，由调用方绑定实际模型网关。
            prompt_version / schema_version / model_version: 出题行为版本，
                与首题一并持久化，供行为可追溯与回归评估。
        """
        self.repository = repository
        if question_generator is None and capabilities is None:
            raise TypeError("question_generator or capabilities is required")
        self.question_generator = question_generator
        self.capabilities = capabilities
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
        """开始一场模拟面试并生成第一题。

        指定 ``resume_analysis_id`` 时校验简历评估存在且已完成，据此
        构建简历上下文用于定向出题；否则按通用方式出题。首题生成在
        持久化之前完成，与面试记录、来源信息、出题版本一起写入。

        参数:
            user_id: 服务端解析的当前用户 ID（所有者）。
            topic: 面试主题。
            level: 难度等级。
            question_count: 本场计划问题总数。
            resume_analysis_id: 可选的简历评估 ID，提供时启用定向面试。

        返回:
            含 ``interview_id``、首题 ``question``、``turn_index=1``、
            ``source_type``（``"resume"`` 或 ``"general"``）等字段的字典；
            简历定向时附带 ``source_resume`` 来源信息。

        异常:
            InterviewSourceNotFound: 指定的简历评估不存在。
            InterviewSourceConflict: 简历评估未完成，不能用于出题。
        """
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
            question = self._generate_question(
                topic=topic,
                level=level,
                turn_index=1,
                previous_turns=[],
                resume_context=context.model_dump(),
            )
        else:
            question = self._generate_question(
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

    def _generate_question(self, **kwargs: Any) -> str:
        if self.capabilities is not None:
            request = QuestionGenerationRequestV1.model_validate(kwargs)
            return self.capabilities.generate(request).question
        assert self.question_generator is not None
        return self.question_generator(**kwargs)


class InterviewAnswerService:
    """处理模拟面试作答：幂等领取、评分、出下一题与原子提交。

    采用 claim/complete 两阶段：先用幂等键领取该轮作答（生成 claim_token
    作为所有者令牌），随后在短事务之外执行评分与出题，最后用 claim_token
    做有条件提交。这样模型调用不进入数据库事务，且迟到的旧请求无法覆盖
    新所有者的结果（所有者封闭 / fencing）。
    """

    def __init__(
        self,
        repository: InterviewAnswerRepository,
        *,
        assessor: Callable[..., dict[str, Any]] | None = None,
        question_generator: Callable[..., str] | None = None,
        capabilities: (QuestionGenerator | AnswerEvaluator) | None = None,
        assessment_prompt_version: str = "interview-assessment-v1",
        assessment_schema_version: str = "assessment-v1",
        model_version: str = "",
    ) -> None:
        """注入持久化仓库与模型回调（评分、出题）。

        参数:
            repository: 实现 ``InterviewAnswerRepository`` 协议的持久化适配器。
            assessor: 评分回调，返回含 ``overall``、``dimensions``、
                ``strengths``、``weaknesses``、``feedback``、
                ``reference_answer`` 的字典。
            question_generator: 出下一题回调。
            assessment_prompt_version / assessment_schema_version /
                model_version: 评分行为版本，与作答结果一起持久化。
        """
        self.repository = repository
        if capabilities is None and (assessor is None or question_generator is None):
            raise TypeError("assessor and question_generator or capabilities are required")
        self.assessor = assessor
        self.question_generator = question_generator
        self.capabilities = capabilities
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
        """提交一题答案：领取 → 评分/出题（事务外）→ 原子提交。

        先用答案摘要与幂等键领取该轮（同一幂等键重放同一答案时直接返回已存
        结果），再把评分与「下一题」放到 Repository 短事务之外执行，最后用
        claim_token 条件提交。任何异常都会用同一 claim_token 把该轮标记为
        失败，保证不会留下「领取中」的死状态。

        参数:
            user_id: 服务端解析的当前用户 ID。
            interview_id: 目标面试 ID。
            answer: 用户作答原文。
            idempotency_key: 客户端幂等键；只允许重放同一答案。

        返回:
            含 ``score``、``dimensions``、``feedback``、``reference_answer``、
            ``next_question``（若无下一题则为 ``None``）、``status``
            （``"active"`` 或 ``"completed"``）等字段的字典。

        异常:
            InterviewAnswerNotFound: 面试不存在。
            InterviewAnswerConflict: 已归档/无待答题/幂等键复用于不同答案/
                他请求正在评分（可重试）/被并发领取等冲突，``retryable``
                标识是否可重试。

        规则:
            claim_token 是所有者封闭令牌；迟到的旧请求不能覆盖新所有者的结果。
            摘要而非原文参与并发比较，避免原文进入日志/比较路径。
        """
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
            assessment = self._assess(
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
                next_question = self._generate_question(**generator_args)

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

    def _assess(self, **kwargs: Any) -> dict[str, Any]:
        if self.capabilities is not None:
            evaluator = self.capabilities
            result = evaluator.evaluate(
                AnswerEvaluationRequestV1.model_validate(kwargs)
            )
            return result.model_dump(
                exclude={"schema_version", "prompt_version", "model_version"}
            )
        assert self.assessor is not None
        return self.assessor(**kwargs)

    def _generate_question(self, **kwargs: Any) -> str:
        if self.capabilities is not None:
            generator = self.capabilities
            return generator.generate(
                QuestionGenerationRequestV1.model_validate(kwargs)
            ).question
        assert self.question_generator is not None
        return self.question_generator(**kwargs)
