import json
from collections import Counter
from typing import Any

from app.interview_engine import DIMENSIONS, DIMENSION_LABELS


def _json_object(value: object) -> dict[str, float]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result = {}
    for key, score in parsed.items():
        try:
            result[str(key)] = float(score)
        except (TypeError, ValueError):
            continue
    return result


def _json_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        str(item).strip()
        for item in parsed
        if str(item).strip()
    ]


def _rounded(value: float) -> float:
    return round(value, 2)


def build_capability_profile(
    rows: list[dict[str, object]],
    *,
    topic: str | None = None,
) -> dict[str, Any]:
    available_topics = sorted(
        {str(row["topic"]).strip() for row in rows if str(row["topic"]).strip()},
        key=str.casefold,
    )
    selected_topic = topic.strip() if topic else None
    filtered_rows = [
        row
        for row in rows
        if not selected_topic
        or str(row["topic"]).casefold() == selected_topic.casefold()
    ]

    interview_groups: dict[str, list[dict[str, object]]] = {}
    topic_groups: dict[str, list[dict[str, object]]] = {}
    weakness_counts: Counter[str] = Counter()
    question_counts: Counter[str] = Counter()
    question_labels: dict[str, str] = {}
    dimension_totals = {name: 0.0 for name in DIMENSIONS}
    dimension_counts = {name: 0 for name in DIMENSIONS}

    for row in filtered_rows:
        interview_id = str(row["interview_id"])
        row_topic = str(row["topic"]).strip()
        interview_groups.setdefault(interview_id, []).append(row)
        topic_groups.setdefault(row_topic, []).append(row)

        dimensions = _json_object(row.get("dimensions_json"))
        for name in DIMENSIONS:
            if name in dimensions:
                dimension_totals[name] += dimensions[name]
                dimension_counts[name] += 1

        weakness_counts.update(_json_list(row.get("weaknesses_json")))
        question = " ".join(str(row.get("question") or "").split())
        if question:
            normalized_question = question.casefold()
            question_counts[normalized_question] += 1
            question_labels.setdefault(normalized_question, question)

    trend = []
    for interview_id, interview_rows in interview_groups.items():
        scores = [float(row["score"]) for row in interview_rows]
        first = interview_rows[0]
        trend.append(
            {
                "interview_id": interview_id,
                "topic": str(first["topic"]),
                "level": str(first["level"]),
                "status": str(first["status"]),
                "answered_questions": len(scores),
                "average_score": _rounded(sum(scores) / len(scores)),
                "updated_at": max(str(row["updated_at"]) for row in interview_rows),
            }
        )
    trend.sort(key=lambda item: str(item["updated_at"]))

    all_scores = [float(row["score"]) for row in filtered_rows]
    completed_interviews = sum(
        1 for item in trend if item["status"] == "completed"
    )
    improvement = (
        _rounded(
            float(trend[-1]["average_score"])
            - float(trend[0]["average_score"])
        )
        if len(trend) > 1
        else 0.0
    )

    topic_breakdown = []
    for row_topic, topic_rows in topic_groups.items():
        topic_scores = [float(row["score"]) for row in topic_rows]
        topic_interviews = {
            str(row["interview_id"]) for row in topic_rows
        }
        topic_breakdown.append(
            {
                "topic": row_topic,
                "interviews": len(topic_interviews),
                "answered_questions": len(topic_scores),
                "average_score": _rounded(
                    sum(topic_scores) / len(topic_scores)
                ),
            }
        )
    topic_breakdown.sort(
        key=lambda item: (
            -int(item["interviews"]),
            -float(item["average_score"]),
            str(item["topic"]).casefold(),
        )
    )

    return {
        "filter": {"topic": selected_topic},
        "available_topics": available_topics,
        "summary": {
            "interviews": len(trend),
            "completed_interviews": completed_interviews,
            "answered_questions": len(filtered_rows),
            "average_score": (
                _rounded(sum(all_scores) / len(all_scores))
                if all_scores
                else 0.0
            ),
            "improvement": improvement,
        },
        "dimension_scores": {
            DIMENSION_LABELS[name]: (
                _rounded(dimension_totals[name] / dimension_counts[name])
                if dimension_counts[name]
                else 0.0
            )
            for name in DIMENSIONS
        },
        "trend": trend,
        "recent_training": list(reversed(trend[-5:])),
        "topic_breakdown": topic_breakdown,
        "weaknesses": [
            {"label": label, "count": count}
            for label, count in weakness_counts.most_common(8)
        ],
        "frequent_questions": [
            {
                "question": question_labels[normalized],
                "count": count,
            }
            for normalized, count in question_counts.most_common(6)
        ],
    }
