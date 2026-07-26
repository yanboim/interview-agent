import json

from app.interview_engine import build_report, parse_assessment


def test_parse_assessment_normalizes_scores():
    assessment = parse_assessment(
        """
        {"overall": 12, "dimensions": {
          "accuracy": 9, "depth": 8, "communication": 11, "practicality": -1
        }, "strengths": ["结构清楚"], "weaknesses": ["缺少指标"],
        "feedback": "补充工程数据", "reference_answer": "参考回答"}
        """
    )

    assert assessment["overall"] == 10
    assert assessment["dimensions"]["communication"] == 10
    assert assessment["dimensions"]["practicality"] == 0
    assert assessment["reference_answer"] == "参考回答"


def test_build_report_finds_weak_dimensions():
    turns = [
        {
            "score": 7.0,
            "dimensions_json": json.dumps(
                {
                    "accuracy": 8,
                    "depth": 5,
                    "communication": 7,
                    "practicality": 4,
                }
            ),
            "weaknesses_json": json.dumps(["缺少项目数据"]),
        },
        {
            "score": 8.0,
            "dimensions_json": json.dumps(
                {
                    "accuracy": 9,
                    "depth": 6,
                    "communication": 8,
                    "practicality": 5,
                }
            ),
            "weaknesses_json": json.dumps(["缺少项目数据"]),
        },
    ]

    report = build_report(turns)

    assert report["average_score"] == 7.5
    assert report["dimension_scores"]["工程实践"] == 4.5
    assert report["weaknesses"] == ["缺少项目数据"]
    assert report["study_plan"][0]["dimension"] == "工程实践"
