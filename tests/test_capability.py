import json

from app.capability import build_capability_profile


def scored_row(
    *,
    interview_id: str,
    topic: str,
    score: float,
    updated_at: str,
    question: str,
    dimensions: dict[str, float],
    weaknesses: list[str],
    status: str = "completed",
    turn_index: int = 1,
) -> dict[str, object]:
    return {
        "interview_id": interview_id,
        "topic": topic,
        "level": "高级",
        "status": status,
        "turn_index": turn_index,
        "question": question,
        "score": score,
        "dimensions_json": json.dumps(dimensions, ensure_ascii=False),
        "weaknesses_json": json.dumps(weaknesses, ensure_ascii=False),
        "updated_at": updated_at,
    }


def test_build_capability_profile_aggregates_across_interviews():
    rows = [
        scored_row(
            interview_id="i-1",
            topic="RAG",
            score=6,
            updated_at="2026-07-01T10:00:00+00:00",
            question="如何评估 RAG？",
            dimensions={
                "accuracy": 7,
                "depth": 5,
                "communication": 7,
                "practicality": 5,
            },
            weaknesses=["缺少忠实度", "缺少线上指标"],
        ),
        scored_row(
            interview_id="i-1",
            topic="RAG",
            score=8,
            updated_at="2026-07-01T10:05:00+00:00",
            question="如何评估 RAG？",
            dimensions={
                "accuracy": 9,
                "depth": 7,
                "communication": 8,
                "practicality": 8,
            },
            weaknesses=["缺少忠实度"],
            turn_index=2,
        ),
        scored_row(
            interview_id="i-2",
            topic="Java",
            score=9,
            updated_at="2026-07-20T10:00:00+00:00",
            question="G1 的回收流程是什么？",
            dimensions={
                "accuracy": 9,
                "depth": 9,
                "communication": 8,
                "practicality": 10,
            },
            weaknesses=[],
        ),
    ]

    profile = build_capability_profile(rows)

    assert profile["available_topics"] == ["Java", "RAG"]
    assert profile["summary"] == {
        "interviews": 2,
        "completed_interviews": 2,
        "answered_questions": 3,
        "average_score": 7.67,
        "improvement": 2.0,
    }
    assert profile["dimension_scores"]["技术准确性"] == 8.33
    assert profile["dimension_scores"]["原理深度"] == 7.0
    assert [item["average_score"] for item in profile["trend"]] == [7.0, 9.0]
    assert profile["weaknesses"][0] == {
        "label": "缺少忠实度",
        "count": 2,
    }
    assert profile["frequent_questions"][0] == {
        "question": "如何评估 RAG？",
        "count": 2,
    }


def test_capability_profile_filters_topic_and_tolerates_bad_json():
    rows = [
        scored_row(
            interview_id="i-1",
            topic="RAG",
            score=7,
            updated_at="2026-07-01T10:00:00+00:00",
            question="RAG",
            dimensions={"accuracy": 7},
            weaknesses=["召回率"],
        ),
        {
            **scored_row(
                interview_id="i-2",
                topic="Java",
                score=9,
                updated_at="2026-07-02T10:00:00+00:00",
                question="JVM",
                dimensions={"accuracy": 9},
                weaknesses=[],
            ),
            "dimensions_json": "{invalid",
            "weaknesses_json": "not-json",
        },
    ]

    profile = build_capability_profile(rows, topic=" java ")

    assert profile["filter"]["topic"] == "java"
    assert profile["available_topics"] == ["Java", "RAG"]
    assert profile["summary"]["interviews"] == 1
    assert profile["summary"]["average_score"] == 9.0
    assert profile["dimension_scores"]["技术准确性"] == 0.0
    assert profile["weaknesses"] == []


def test_empty_capability_profile_has_stable_shape():
    profile = build_capability_profile([])

    assert profile["summary"]["answered_questions"] == 0
    assert profile["dimension_scores"] == {
        "技术准确性": 0.0,
        "原理深度": 0.0,
        "表达结构": 0.0,
        "工程实践": 0.0,
    }
    assert profile["trend"] == []
