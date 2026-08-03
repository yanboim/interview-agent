"""模型/Agent 路由、灰度与回退策略的测试。"""

import json
from pathlib import Path

import pytest

from app.agent_budget import AgentBudgetState
from app.config import Settings
from app.model_gateway import ModelBudgetExceeded, create_chat_model
from app.model_routing import (
    ModelUnavailable,
    call_with_fallback,
    classify_intent,
    explicit_workflow_routes,
    fallback_policy,
    model_for_purpose,
)


def _settings(**overrides):
    values = {
        "zhipu_api_key": "test-key",
        "zhipu_model": "primary-v1",
        "llm_input_char_budget": 100,
        "llm_max_concurrency": 1,
    }
    values.update(overrides)
    return Settings(**values)


def test_purpose_models_default_and_override_independently():
    settings = _settings(
        llm_model_knowledge="knowledge-v2",
        llm_model_schema_repair="repair-v1",
    )

    assert model_for_purpose(settings, "knowledge") == "knowledge-v2"
    assert model_for_purpose(settings, "planner") == "primary-v1"
    model = create_chat_model("knowledge", temperature=0, settings=settings)
    assert model.model_name == "knowledge-v2"
    assert model.for_schema_repair().model_name == "repair-v1"


def test_classifier_only_directs_high_confidence_single_intent():
    direct = classify_intent("请给我的回答评分并指出错误")
    ambiguous = classify_intent("先解释 RAG 原理，再出题考我")
    unknown = classify_intent("你好")

    assert direct.specialist == "evaluator" and direct.confidence >= 0.9
    assert ambiguous.specialist is None and ambiguous.multi_intent
    assert unknown.specialist is None


def test_explicit_workflow_routes_multi_intent_in_bounded_dependency_order():
    assert explicit_workflow_routes("先评价回答并指出错误，再追问一道题") == (
        "evaluator",
        "interviewer",
    )
    assert explicit_workflow_routes("你好") == ("knowledge",)


def test_fallback_requires_approval_and_blocks_uncalibrated_high_impact_models():
    settings = _settings(
        llm_fallback_enabled=True,
        llm_fallback_evaluation_approved=True,
        llm_fallback_model="same-provider-fallback-v1",
        llm_fallback_approved_purposes="knowledge,planner",
    )
    knowledge = fallback_policy(settings, "knowledge")
    evaluator = fallback_policy(settings, "evaluator")

    assert call_with_fallback(
        lambda: (_ for _ in ()).throw(RuntimeError("primary down")),
        lambda: "fallback result",
        policy=knowledge,
    ) == "fallback result"
    assert not evaluator.allowed and evaluator.reason == "uncalibrated_high_impact"
    with pytest.raises(ModelUnavailable, match="uncalibrated_high_impact"):
        call_with_fallback(
            lambda: (_ for _ in ()).throw(RuntimeError("primary down")),
            lambda: "must not run",
            policy=evaluator,
        )


def test_request_budget_stops_before_an_additional_call_and_tracks_cost():
    budget = AgentBudgetState(
        request_class="chat", price_version="p1", max_calls=1,
        max_total_tokens=100, max_cost_usd=1.0,
        input_usd_per_million=2.0, output_usd_per_million=4.0,
        started_at=0,
    )
    budget.claim_call("knowledge")
    budget.record_usage(20, 10)

    assert budget.snapshot()["call_count"] == 1
    assert budget.snapshot()["cost_usd"] == 0.00008
    with pytest.raises(ModelBudgetExceeded, match="before knowledge"):
        budget.claim_call("knowledge")


def test_approved_canary_report_has_no_quality_privacy_or_completion_regression():
    report = json.loads(
        Path("eval/reports/model-routing-canary-approved.json").read_text()
    )
    assert report["approval_status"] == "approved"
    assert report["rollback_verified"] is True
    assert report["zero_tolerance_failures"] == 0
    assert report["routed"]["quality_pass_rate"] >= report["baseline"]["quality_pass_rate"]
    assert report["routed"]["completion_rate"] >= report["baseline"]["completion_rate"]
    assert report["routed"]["p95_latency_ms"] <= report["baseline"]["p95_latency_ms"]
    assert report["routed"]["cost_per_completed_training_action_usd"] <= report["baseline"]["cost_per_completed_training_action_usd"]
