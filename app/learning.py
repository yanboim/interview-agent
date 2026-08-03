"""把能力薄弱项转换为可去重的学习候选，并计算确定性的复习时间。"""

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
    """把能力画像的薄弱维度与弱点转化为可去重的学习任务候选。

    优先取评分最低的两个能力维度，按 ``DIMENSION_ACTIONS`` 给出对应
    训练动作；再补充最薄弱维度下的前三条弱点作为案例式复习。最终按
    ``(维度, 弱点)`` 的小写键去重，避免同一薄弱点重复出现。

    参数:
        profile: 能力画像，至少包含 ``dimension_scores``（或
            ``calibrated_dimension_scores``，校准后优先）与
            ``weaknesses``（``{"label": str}``` 列表）。

    返回:
        学习候选列表，每项为
        ``{"dimension", "weakness", "action"}``。
    """
    candidates: list[dict[str, str]] = []
    dimension_scores = profile.get("calibrated_dimension_scores") or profile[
        "dimension_scores"
    ]
    dimensions = sorted(
        dimension_scores.items(),
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
    outcome: str = "remembered",
    difficulty: int = 3,
    lapse_count: int = 0,
    confidence: float = 0.5,
) -> datetime:
    """计算下次间隔复习时间。

    在 ``REVIEW_INTERVAL_DAYS`` 基础间隔上叠加多个调节因子，模拟
    间隔重复（spaced repetition）：回忆结果越好、题目越简单、用户
    越有信心、遗忘越少，间隔越长。

    参数:
        review_count: 已完成的复习次数，用于索引基础间隔。
        now: 起算时刻，默认当前 UTC 时间；可注入便于测试。
        outcome: 上次回忆结果，``"remembered"`` / ``"partial"`` /
            ``"forgotten"`` 之一，未知值按 ``"partial"`` 处理。
        difficulty: 难度 ``1-5``，越难间隔越短；越界会被钳制。
        lapse_count: 已遗忘次数，越多间隔越短。
        confidence: 自评信心 ``0.0-1.0``，越有信心间隔越长；越界会被钳制。

    返回:
        下次复习时刻（带 UTC 时区信息）。最终天数被钳制在 ``[1, 60]``。

    规则:
        所有因子相乘后四舍五入到整数天，确保最小 1 天、最大 60 天。
    """
    current = now or datetime.now(UTC)
    interval_index = min(
        max(review_count - 1, 0),
        len(REVIEW_INTERVAL_DAYS) - 1,
    )
    base_days = REVIEW_INTERVAL_DAYS[interval_index]
    outcome_factor = {
        "remembered": 1.0,
        "partial": 0.45,
        "forgotten": 0.15,
    }.get(outcome, 0.45)
    difficulty_factor = 1.3 - min(5, max(1, difficulty)) * 0.1
    confidence_factor = 0.75 + min(1.0, max(0.0, confidence)) * 0.5
    lapse_factor = max(0.35, 1.0 - max(0, lapse_count) * 0.12)
    days = round(
        base_days
        * outcome_factor
        * difficulty_factor
        * confidence_factor
        * lapse_factor
    )
    return current + timedelta(days=max(1, min(60, days)))
