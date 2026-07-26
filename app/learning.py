from datetime import UTC, datetime, timedelta
from typing import Any


DIMENSION_ACTIONS = {
    "技术准确性": "整理核心概念、边界条件和常见误区，并用三分钟重新回答。",
    "原理深度": "补充底层机制、关键流程和设计取舍，画一张原理图后复述。",
    "表达结构": "使用“结论—原理—案例—权衡”结构录制一次完整回答。",
    "工程实践": "补充真实项目场景、量化指标、故障处理和最终效果。",
}

REVIEW_INTERVAL_DAYS = (1, 3, 7, 14, 30, 60)


def build_learning_candidates(
    profile: dict[str, Any],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    dimensions = sorted(
        profile["dimension_scores"].items(),
        key=lambda item: (float(item[1]), item[0]),
    )
    for dimension, score in dimensions[:2]:
        if float(score) <= 0:
            continue
        candidates.append(
            {
                "dimension": str(dimension),
                "weakness": f"{dimension}当前平均分 {score}",
                "action": DIMENSION_ACTIONS.get(
                    str(dimension),
                    "围绕该能力完成一次专项复习和口头复述。",
                ),
            }
        )

    weakest_dimension = dimensions[0][0] if dimensions else "综合能力"
    for item in profile["weaknesses"][:3]:
        weakness = str(item["label"])
        candidates.append(
            {
                "dimension": str(weakest_dimension),
                "weakness": weakness,
                "action": (
                    f"针对“{weakness}”整理一页笔记，补充一个项目案例，"
                    "并完成一次两分钟脱稿回答。"
                ),
            }
        )

    unique = {}
    for candidate in candidates:
        key = (
            candidate["dimension"].casefold(),
            candidate["weakness"].casefold(),
        )
        unique.setdefault(key, candidate)
    return list(unique.values())


def next_review_time(
    review_count: int,
    *,
    now: datetime | None = None,
) -> datetime:
    current = now or datetime.now(UTC)
    interval_index = min(
        max(review_count - 1, 0),
        len(REVIEW_INTERVAL_DAYS) - 1,
    )
    return current + timedelta(days=REVIEW_INTERVAL_DAYS[interval_index])
