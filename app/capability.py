"""跨面试聚合能力画像；输出由持久评分确定性计算，不依赖外部服务。"""

import json
import math
from collections import Counter
from datetime import datetime
from typing import Any

from app.interview_engine import DIMENSIONS, DIMENSION_LABELS

CALIBRATION_VERSION = "human-labelled-v1"
MODEL_SCORE_OFFSETS = {
    "interview-assessment-v1": -0.2,
    "interview-review-v1": -0.1,
}


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


def _confidence(sample_count: int) -> float:
    return _rounded(min(0.95, sample_count / (sample_count + 5)))


def _recency_weights(rows: list[dict[str, object]]) -> list[float]:
    parsed = []
    for row in rows:
        try:
            parsed.append(datetime.fromisoformat(str(row["updated_at"])))
        except (KeyError, TypeError, ValueError):
            parsed.append(None)
    valid = [item for item in parsed if item is not None]
    if not valid:
        return [1.0] * len(rows)
    latest = max(valid)
    return [
        math.exp(-max(0.0, (latest - item).total_seconds()) / (90 * 86400))
        if item is not None else 0.5
        for item in parsed
    ]


def score_calibration_report(examples: list[dict[str, object]]) -> dict[str, object]:
    """把持久化的模型评分与经隐私评审的人工标注对比，输出校准报告。

    参数:
        examples: 各样本含 ``model_version``、``model_score``、``human_score``。

    返回:
        校准报告（含样本数、置信度、平均偏差、MAE、RMSE 及各模型分群偏差）。
    """
    rows = [
        (
            str(item.get("model_version") or "unknown"),
            float(item["model_score"]),
            float(item["human_score"]),
        )
        for item in examples
    ]
    errors = [predicted - human for _, predicted, human in rows]
    cohorts: dict[str, list[float]] = {}
    for model, predicted, human in rows:
        cohorts.setdefault(model, []).append(predicted - human)
    count = len(rows)
    return {
        "schema_version": "capability-calibration-report-v1",
        "calibration_version": CALIBRATION_VERSION,
        "sample_count": count,
        "confidence": _confidence(count),
        "mean_bias": _rounded(sum(errors) / count) if count else 0.0,
        "mean_absolute_error": (
            _rounded(sum(abs(error) for error in errors) / count) if count else 0.0
        ),
        "root_mean_squared_error": (
            _rounded(math.sqrt(sum(error * error for error in errors) / count))
            if count else 0.0
        ),
        "model_cohorts": {
            model: {
                "sample_count": len(values),
                "confidence": _confidence(len(values)),
                "mean_bias": _rounded(sum(values) / len(values)),
            }
            for model, values in sorted(cohorts.items())
        },
    }


def build_capability_profile(
    rows: list[dict[str, object]],
    *,
    topic: str | None = None,
) -> dict[str, Any]:
    """跨面试聚合能力画像：维度评分、趋势、薄弱点、高频题与校准信息。

    全部由持久评分确定性计算，不依赖外部服务。维度评分可按模型版本做
    偏移校准并按近邻加权，缓解旧评分与不同模型版本带来的偏差。

    参数:
        rows: 用户的面试回合评分行。
        topic: 可选主题过滤；为空时聚合全部。

    返回:
        能力画像字典，含 summary/dimension_scores/calibrated_dimension_scores/
        trend/topic_breakdown/weaknesses/frequent_questions 等。
    """
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
    calibrated_dimension_totals = {name: 0.0 for name in DIMENSIONS}
    calibrated_dimension_weights = {name: 0.0 for name in DIMENSIONS}
    recency_weights = _recency_weights(filtered_rows)

    for row, recency_weight in zip(filtered_rows, recency_weights, strict=True):
        interview_id = str(row["interview_id"])
        row_topic = str(row["topic"]).strip()
        interview_groups.setdefault(interview_id, []).append(row)
        topic_groups.setdefault(row_topic, []).append(row)

        dimensions = _json_object(row.get("dimensions_json"))
        model_version = str(row.get("assessment_model_version") or "unknown")
        score_offset = MODEL_SCORE_OFFSETS.get(model_version, 0.0)
        for name in DIMENSIONS:
            if name in dimensions:
                dimension_totals[name] += dimensions[name]
                dimension_counts[name] += 1
                calibrated_dimension_totals[name] += min(
                    10.0, max(0.0, dimensions[name] + score_offset)
                ) * recency_weight
                calibrated_dimension_weights[name] += recency_weight

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
                "source_type": str(first.get("source_type") or "general"),
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

    def cohort_rows(field: str) -> list[dict[str, object]]:
        groups: dict[str, list[tuple[dict[str, object], float]]] = {}
        for row, weight in zip(filtered_rows, recency_weights, strict=True):
            label = str(row.get(field) or "unknown")
            groups.setdefault(label, []).append((row, weight))
        result = []
        for label, members in sorted(groups.items()):
            weighted = sum(float(row["score"]) * weight for row, weight in members)
            total_weight = sum(weight for _, weight in members)
            result.append({
                "cohort": label,
                "sample_count": len(members),
                "confidence": _confidence(len(members)),
                "recency_weighted_score": _rounded(weighted / total_weight),
            })
        return result

    weighted_score_total = sum(
        float(row["score"]) * weight
        for row, weight in zip(filtered_rows, recency_weights, strict=True)
    )
    total_recency_weight = sum(recency_weights)

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
        "calibrated_dimension_scores": {
            DIMENSION_LABELS[name]: (
                _rounded(
                    calibrated_dimension_totals[name]
                    / calibrated_dimension_weights[name]
                )
                if calibrated_dimension_weights[name]
                else 0.0
            )
            for name in DIMENSIONS
        },
        "calibration": {
            "version": CALIBRATION_VERSION,
            "sample_count": len(filtered_rows),
            "confidence": _confidence(len(filtered_rows)),
            "recency_weighted_score": (
                _rounded(weighted_score_total / total_recency_weight)
                if total_recency_weight else 0.0
            ),
            "cohorts": {
                "topic": cohort_rows("topic"),
                "difficulty": cohort_rows("level"),
                "model_version": cohort_rows("assessment_model_version"),
            },
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
