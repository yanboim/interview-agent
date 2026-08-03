"""学习候选生成与间隔复习时间计算的测试。"""

from datetime import UTC, datetime

from app.learning import build_learning_candidates, next_review_time
from app.storage import ConversationStore


def test_learning_candidates_use_weak_dimensions_and_weaknesses():
    profile = {
        "dimension_scores": {
            "技术准确性": 8.0,
            "原理深度": 5.0,
            "表达结构": 6.0,
            "工程实践": 4.0,
        },
        "weaknesses": [
            {"label": "缺少项目数据", "count": 3},
            {"label": "没有说明权衡", "count": 2},
        ],
    }

    candidates = build_learning_candidates(profile)

    assert candidates[0]["dimension"] == "工程实践"
    assert candidates[1]["dimension"] == "原理深度"
    assert any(item["weakness"] == "缺少项目数据" for item in candidates)
    assert all(item["action"] for item in candidates)


def test_review_schedule_expands_with_repetition():
    now = datetime(2026, 7, 24, tzinfo=UTC)

    first = next_review_time(1, now=now)
    third = next_review_time(3, now=now)
    mature = next_review_time(20, now=now)

    assert (first - now).days == 1
    assert (third - now).days == 7
    assert (mature - now).days == 60


def test_review_schedule_uses_outcome_difficulty_lapses_and_confidence():
    now = datetime(2026, 7, 24, tzinfo=UTC)

    remembered = next_review_time(
        4, now=now, outcome="remembered", difficulty=1,
        lapse_count=0, confidence=0.9,
    )
    partial = next_review_time(
        4, now=now, outcome="partial", difficulty=3,
        lapse_count=1, confidence=0.5,
    )
    forgotten = next_review_time(
        4, now=now, outcome="forgotten", difficulty=5,
        lapse_count=2, confidence=0.2,
    )

    assert remembered > partial > forgotten
    assert (forgotten - now).days >= 1
    assert (remembered - now).days <= 60


def test_learning_plan_preview_requires_owner_confirmation_and_replays(tmp_path):
    store = ConversationStore(tmp_path / "learning-confirmation.db")
    candidates = [
        {
            "dimension": "工程实践",
            "weakness": "缺少故障复盘",
            "action": "补充一次真实故障的指标、处置和复盘。",
        }
    ]

    preview = store.create_learning_plan_preview(
        user_id="user-a",
        topic="分布式系统",
        candidates=candidates,
    )

    assert store.list_learning_tasks(user_id="user-a") == []
    assert (
        store.confirm_learning_plan(
            user_id="user-b",
            confirmation_id=str(preview["confirmation_id"]),
        )
        is None
    )
    assert store.list_learning_tasks(user_id="user-a") == []

    applied = store.confirm_learning_plan(
        user_id="user-a",
        confirmation_id=str(preview["confirmation_id"]),
    )
    replayed = store.confirm_learning_plan(
        user_id="user-a",
        confirmation_id=str(preview["confirmation_id"]),
    )

    assert applied is not None
    assert applied["status"] == "applied"
    assert replayed == applied
    assert len(store.list_learning_tasks(user_id="user-a")) == 1
