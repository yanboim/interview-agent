from datetime import UTC, datetime

from app.learning import build_learning_candidates, next_review_time


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
