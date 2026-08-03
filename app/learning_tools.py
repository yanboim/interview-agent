"""Authenticated learning-tool application logic without Agent framework coupling."""

import json
from typing import Any

from app.agent_contracts import TrainingPlanPreviewV1
from app.capability import build_capability_profile
from app.learning import build_learning_candidates


def learning_progress(store: Any, *, user_id: str, topic: str = "") -> str:
    rows = store.get_capability_rows(user_id=user_id)
    profile = build_capability_profile(rows, topic=topic or None)
    tasks = store.list_learning_tasks(user_id=user_id)
    task_counts = {
        status: sum(1 for item in tasks if item["status"] == status)
        for status in ("todo", "in_progress", "completed")
    }
    return json.dumps(
        {
            "summary": profile["summary"],
            "dimension_scores": profile["dimension_scores"],
            "weaknesses": profile["weaknesses"][:5],
            "learning_tasks": task_counts,
        },
        ensure_ascii=False,
    )


def learning_plan_preview(store: Any, *, user_id: str, topic: str = "") -> str:
    rows = store.get_capability_rows(user_id=user_id)
    profile = build_capability_profile(rows, topic=topic or None)
    candidates = build_learning_candidates(profile)
    if not candidates:
        return "暂无足够的面试评分，无法生成学习计划。"
    preview = store.create_learning_plan_preview(
        user_id=user_id, topic=topic, candidates=candidates
    )
    validated = TrainingPlanPreviewV1.model_validate(preview)
    return json.dumps(
        {
            **validated.model_dump(),
            "instruction": (
                "尚未创建任务。仅当用户明确确认这份预览时，调用 "
                "confirm_personal_learning_plan。"
            ),
        },
        ensure_ascii=False,
    )


def confirm_learning_plan(
    store: Any, *, user_id: str, confirmation_id: str
) -> str:
    result = store.confirm_learning_plan(
        user_id=user_id, confirmation_id=confirmation_id.strip()
    )
    if result is None:
        return "未找到当前用户可确认的学习计划。"
    return json.dumps(result, ensure_ascii=False)
