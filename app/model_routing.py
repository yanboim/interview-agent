"""Deterministic model/Agent routing, rollout, fallback, and request budgets."""

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar


PURPOSES = (
    "supervisor", "knowledge", "interviewer", "evaluator", "planner",
    "summarization", "schema_repair",
)
HIGH_IMPACT_PURPOSES = {"evaluator", "resume_analysis", "interview_review"}


@dataclass(frozen=True)
class IntentDecision:
    specialist: Literal["knowledge", "interviewer", "evaluator", "planner"] | None
    confidence: float
    multi_intent: bool


def classify_intent(text: str) -> IntentDecision:
    normalized = " ".join(text.casefold().split())
    keywords = {
        "evaluator": ("评分", "评价", "错误", "遗漏", "几分", "改进回答"),
        "interviewer": ("出题", "模拟面试", "考我", "追问", "下一题"),
        "planner": ("学习计划", "复习计划", "能力画像", "历次", "训练安排"),
        "knowledge": ("解释", "原理", "知识库", "是什么", "如何设计", "对比"),
    }
    scores = {
        name: sum(keyword in normalized for keyword in words)
        for name, words in keywords.items()
    }
    matched = [name for name, score in scores.items() if score > 0]
    if len(matched) != 1:
        return IntentDecision(None, 0.5 if matched else 0.0, len(matched) > 1)
    specialist = matched[0]
    score = scores[specialist]
    confidence = 0.97 if score >= 2 else 0.9
    return IntentDecision(specialist, confidence, False)  # type: ignore[arg-type]


def rollout_allows_direct_route(
    *, stage: str, user_id: str, role: str, canary_percent: int
) -> bool:
    if stage == "production":
        return True
    if stage == "internal":
        return role == "admin"
    if stage == "canary":
        bucket = int(hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8], 16) % 100
        return bucket < max(0, min(100, canary_percent))
    return False


def model_for_purpose(settings: Any, purpose: str) -> str:
    configured = getattr(settings, f"llm_model_{purpose}", "")
    return str(configured or settings.zhipu_model)


@dataclass(frozen=True)
class FallbackPolicy:
    purpose: str
    primary_model: str
    fallback_model: str | None
    allowed: bool
    reason: str


def fallback_policy(settings: Any, purpose: str) -> FallbackPolicy:
    primary = model_for_purpose(settings, purpose)
    fallback = str(getattr(settings, "llm_fallback_model", "") or "")
    approved = {
        item.strip()
        for item in str(getattr(settings, "llm_fallback_approved_purposes", "")).split(",")
        if item.strip()
    }
    enabled = bool(getattr(settings, "llm_fallback_enabled", False)) and bool(
        getattr(settings, "llm_fallback_evaluation_approved", False)
    )
    if purpose in HIGH_IMPACT_PURPOSES:
        return FallbackPolicy(purpose, primary, None, False, "uncalibrated_high_impact")
    allowed = enabled and bool(fallback) and fallback != primary and purpose in approved
    return FallbackPolicy(
        purpose, primary, fallback if allowed else None, allowed,
        "approved" if allowed else "disabled_or_unapproved",
    )


ResultT = TypeVar("ResultT")


class ModelUnavailable(RuntimeError):
    """Recoverable provider-unavailable state after policy-approved attempts."""


def call_with_fallback(
    primary: Callable[[], ResultT],
    fallback: Callable[[], ResultT] | None,
    *,
    policy: FallbackPolicy,
) -> ResultT:
    try:
        return primary()
    except Exception as primary_error:
        if not policy.allowed or fallback is None:
            raise ModelUnavailable(
                f"{policy.purpose} model unavailable ({policy.reason})"
            ) from primary_error
        try:
            return fallback()
        except Exception as fallback_error:
            raise ModelUnavailable(
                f"{policy.purpose} primary and fallback unavailable"
            ) from fallback_error
