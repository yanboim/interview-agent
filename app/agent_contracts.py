"""Versioned data contracts shared by agent/model application boundaries."""

import json
from collections.abc import Sequence
from typing import Any, Literal, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


AGENT_SCHEMA_VERSION = "agent-schema-v1"
ASSESSMENT_SCHEMA_VERSION = "assessment-v1"
RESUME_ANALYSIS_SCHEMA_VERSION = "resume-analysis-v1"
INTERVIEW_REVIEW_SCHEMA_VERSION = "interview-review-v1"
CITATION_SCHEMA_VERSION = 1


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DelegationDecisionV1(StrictContract):
    schema_version: Literal["agent-schema-v1"] = AGENT_SCHEMA_VERSION
    specialists: list[
        Literal["knowledge", "interviewer", "evaluator", "planner"]
    ] = Field(min_length=1, max_length=4)
    rationale: str = Field(min_length=1, max_length=1000)


class DelegationEnvelopeV1(StrictContract):
    schema_version: Literal["delegation-envelope-v1"] = "delegation-envelope-v1"
    user_goal: str = Field(min_length=1, max_length=5000)
    original_request: str = Field(min_length=1, max_length=5000)
    relevant_prior_turns: list[dict[str, str]] = Field(
        default_factory=list, max_length=8
    )
    evidence: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    expected_output_schema: str = "SpecialistResultV1"
    request_id: str = Field(default="", max_length=128)
    interaction_id: str = Field(default="", max_length=256)
    context: dict[str, Any] = Field(default_factory=dict)


class EvidenceSourceV1(StrictContract):
    evidence_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=500)
    kind: Literal["private", "public"]
    url: str | None = Field(default=None, max_length=2000)


class AnswerCitationV1(StrictContract):
    claim: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    support: Literal["supported", "unsupported", "conflicting"]


class SpecialistResultV1(StrictContract):
    schema_version: Literal["agent-schema-v1"] = AGENT_SCHEMA_VERSION
    answer: str = Field(min_length=1, max_length=50_000)
    citations: list[AnswerCitationV1] = Field(default_factory=list)
    sources: list[EvidenceSourceV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def citations_reference_known_sources(self) -> "SpecialistResultV1":
        known = {source.evidence_id for source in self.sources}
        referenced = {
            evidence_id
            for citation in self.citations
            for evidence_id in citation.evidence_ids
        }
        unknown = sorted(referenced - known)
        if unknown:
            raise ValueError(f"citations reference unknown evidence: {unknown}")
        return self


class AssessmentV1(StrictContract):
    overall: float
    dimensions: dict[str, float]
    strengths: list[str] = Field(default_factory=list, max_length=5)
    weaknesses: list[str] = Field(default_factory=list, max_length=5)
    feedback: str = Field(default="", max_length=20_000)
    reference_answer: str = Field(default="", max_length=30_000)

    @model_validator(mode="after")
    def require_dimensions(self) -> "AssessmentV1":
        required = {"accuracy", "depth", "communication", "practicality"}
        if set(self.dimensions) != required:
            raise ValueError("assessment dimensions must match the v1 contract")
        return self


class TrainingPlanItemV1(StrictContract):
    dimension: str = Field(min_length=1, max_length=100)
    weakness: str = Field(min_length=1, max_length=300)
    action: str = Field(min_length=1, max_length=5000)


class TrainingPlanPreviewV1(StrictContract):
    schema_version: Literal["agent-schema-v1"] = AGENT_SCHEMA_VERSION
    confirmation_id: str = Field(min_length=1, max_length=128)
    status: Literal["awaiting_confirmation"]
    topic: str = Field(default="", max_length=500)
    candidates: list[TrainingPlanItemV1] = Field(min_length=1, max_length=20)
    expires_at: str = Field(min_length=1, max_length=40)


class StructuredOutputError(ValueError):
    """The model failed the declared schema after one bounded repair."""


ContractT = TypeVar("ContractT", bound=BaseModel)


def parse_single_json_object(content: str) -> dict[str, Any]:
    """Parse exactly one JSON object; reject truncation and extra objects."""
    normalized = content.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise StructuredOutputError("unterminated JSON fence")
        normalized = "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(normalized)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("invalid or truncated JSON") from exc
    if normalized[end:].strip():
        raise StructuredOutputError("multiple objects or trailing content")
    if not isinstance(value, dict):
        raise StructuredOutputError("structured output must be a JSON object")
    return value


def validate_structured_text(
    content: str,
    schema: type[ContractT],
) -> ContractT:
    try:
        return schema.model_validate(parse_single_json_object(content))
    except ValidationError as exc:
        raise StructuredOutputError("structured output schema mismatch") from exc


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    return content.strip() if isinstance(content, str) else str(content).strip()


def invoke_structured(
    model: Any,
    messages: Sequence[BaseMessage],
    schema: type[ContractT],
) -> ContractT:
    """Invoke a model and permit exactly one bounded schema-repair call."""
    profile = getattr(model, "profile", None) or {}
    if isinstance(profile, dict) and profile.get("structured_output"):
        try:
            native = model.with_structured_output(schema, method="json_schema")
            result = native.invoke(list(messages))
            return result if isinstance(result, schema) else schema.model_validate(result)
        except (ValidationError, ValueError, TypeError) as exc:
            raise StructuredOutputError("native structured output schema mismatch") from exc
    response = model.invoke(list(messages))
    content = _message_text(response)
    try:
        return validate_structured_text(content, schema)
    except StructuredOutputError as first_error:
        repair_model = (
            model.for_schema_repair()
            if callable(getattr(model, "for_schema_repair", None))
            else model
        )
        repair = repair_model.invoke(
            [
                SystemMessage(
                    content=(
                        "你是结构化输出修复器。只返回一个满足给定JSON Schema的"
                        "JSON对象，不添加Markdown、解释或第二个对象。不得补充原输出"
                        "中不存在的事实；无法确定的可选字段使用空值。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"JSON Schema：{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
                        f"待修复输出：{content[:12000]}"
                    )
                ),
            ]
        )
        try:
            return validate_structured_text(_message_text(repair), schema)
        except StructuredOutputError as repair_error:
            raise StructuredOutputError(
                "model output failed schema after one repair"
            ) from repair_error
