"""Versioned application contracts for interview questions and assessments."""

from typing import Any, Literal, Protocol

from pydantic import Field

from app.agent_contracts import AssessmentV1, StrictContract


QUESTION_PROMPT_VERSION = "interview-question-v1"
QUESTION_SCHEMA_VERSION = "question-text-v1"
ASSESSMENT_PROMPT_VERSION = "interview-assessment-v1"
ASSESSMENT_SCHEMA_VERSION = "assessment-v1"
REPORT_SCHEMA_VERSION = "interview-report-v1"

ASSESSMENT_DIMENSIONS = (
    "accuracy",
    "depth",
    "communication",
    "practicality",
)
ASSESSMENT_RUBRIC_ZH = "技术准确性、原理深度、表达结构和工程实践"

QUESTION_SYSTEM_PROMPT = (
    "你是一名高级软件工程师面试官。一次只提出一个清晰、可评分的"
    "中文技术问题，不要给答案、提示或评分标准。避免与历史问题重复。"
    "如有简历上下文，问题必须关联其中的项目证据或岗位差距。"
)
ASSESSMENT_SYSTEM_PROMPT = (
    "你是严格但建设性的高级工程师面试评分官。按技术准确性、原理深度、"
    "表达结构和工程实践四个维度评分，指出具体优点、错误、遗漏与改进建议。"
)


class QuestionGenerationRequestV1(StrictContract):
    schema_version: Literal["question-request-v1"] = "question-request-v1"
    topic: str = Field(min_length=1, max_length=500)
    level: str = Field(min_length=1, max_length=100)
    turn_index: int = Field(ge=1)
    previous_turns: list[dict[str, Any]] = Field(default_factory=list)
    resume_context: dict[str, Any] | None = None


class QuestionGenerationResultV1(StrictContract):
    schema_version: Literal["question-text-v1"] = QUESTION_SCHEMA_VERSION
    prompt_version: str = QUESTION_PROMPT_VERSION
    model_version: str = ""
    question: str = Field(min_length=1, max_length=20_000)


class AnswerEvaluationRequestV1(StrictContract):
    schema_version: Literal["assessment-request-v1"] = "assessment-request-v1"
    topic: str = Field(min_length=1, max_length=500)
    level: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=20_000)
    answer: str = Field(min_length=1, max_length=50_000)


class AnswerEvaluationResultV1(AssessmentV1):
    schema_version: Literal["assessment-v1"] = ASSESSMENT_SCHEMA_VERSION
    prompt_version: str = ASSESSMENT_PROMPT_VERSION
    model_version: str = ""


class InterviewReportV1(StrictContract):
    schema_version: Literal["interview-report-v1"] = REPORT_SCHEMA_VERSION
    average_score: float
    dimension_scores: dict[str, float]
    weaknesses: list[str]
    study_plan: list[dict[str, Any]]


class QuestionGenerator(Protocol):
    def generate(
        self, request: QuestionGenerationRequestV1
    ) -> QuestionGenerationResultV1: ...


class AnswerEvaluator(Protocol):
    def evaluate(
        self, request: AnswerEvaluationRequestV1
    ) -> AnswerEvaluationResultV1: ...


class InterviewReportBuilder(Protocol):
    def build(self, turns: list[dict[str, object]]) -> InterviewReportV1: ...


class InterviewCapabilities(
    QuestionGenerator, AnswerEvaluator, InterviewReportBuilder, Protocol
):
    """Combined port used when one adapter owns all interview model behavior."""
