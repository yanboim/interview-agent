"""确定性的模型/Agent 路由、灰度发布、回退策略与用途预算声明。"""

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar


HIGH_IMPACT_PURPOSES = {"evaluator", "resume_analysis", "interview_review"}


@dataclass(frozen=True)
class IntentDecision:
    """意图分类结果：命中专家、置信度、是否多意图。"""

    specialist: Literal["knowledge", "interviewer", "evaluator", "planner"] | None
    confidence: float
    multi_intent: bool


def classify_intent(text: str) -> IntentDecision:
    """用关键词匹配把消息归类为单一专家（无模型、确定性）。

    多个专家同时命中或都不命中时返回 ``multi_intent=True`` 与 ``None`` 专家；
    Workflow V2 使用 ``explicit_workflow_routes`` 生成完整有界路由。
    """
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


def explicit_workflow_routes(text: str) -> tuple[str, ...]:
    """返回显式 Workflow V2 的有界、确定性专家执行顺序。

    评分先于追问，知识解释先于训练安排；未命中关键词时由 knowledge 专家
    处理通用请求。最多四个已批准专家，不生成开放式模型计划。
    """
    normalized = " ".join(text.casefold().split())
    keywords = {
        "evaluator": ("评分", "评价", "错误", "遗漏", "几分", "改进回答"),
        "knowledge": ("解释", "原理", "知识库", "是什么", "如何设计", "对比"),
        "interviewer": ("出题", "模拟面试", "考我", "追问", "下一题"),
        "planner": ("学习计划", "复习计划", "能力画像", "历次", "训练安排"),
    }
    routes = tuple(
        name
        for name in ("evaluator", "knowledge", "interviewer", "planner")
        if any(keyword in normalized for keyword in keywords[name])
    )
    return routes or ("knowledge",)


def model_for_purpose(settings: Any, purpose: str) -> str:
    """返回某用途配置的模型名，未单独配置时回退到默认 ``zhipu_model``。"""
    configured = getattr(settings, f"llm_model_{purpose}", "")
    return str(configured or settings.zhipu_model)


@dataclass(frozen=True)
class FallbackPolicy:
    """模型回退策略：主模型、回退模型、是否允许回退及原因。"""

    purpose: str
    primary_model: str
    fallback_model: str | None
    allowed: bool
    reason: str


def fallback_policy(settings: Any, purpose: str) -> FallbackPolicy:
    """计算某用途的回退策略。

    高影响用途（评分类）永不回退（未校准风险）；其余用途仅在开关、审批名单、
    回退模型已配置且与主模型不同时才允许回退。
    """
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
    """在策略允许的尝试都失败后，可恢复的「供应商不可用」状态。"""


def call_with_fallback(
    primary: Callable[[], ResultT],
    fallback: Callable[[], ResultT] | None,
    *,
    policy: FallbackPolicy,
) -> ResultT:
    """先调主模型，失败且策略允许时回退；两者都失败抛 ``ModelUnavailable``。"""
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
