import json
from pathlib import Path

from scripts.evaluate_resume_interviews import evaluate_question_cases


def test_resume_interview_question_fixture_meets_baseline() -> None:
    cases = [
        json.loads(line)
        for line in Path(
            "eval/resume_interview_questions.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    report = evaluate_question_cases(cases)

    assert report["summary"] == {
        "cases": 1,
        "questions": 6,
        "evidence_link_rate": 1.0,
        "type_coverage": 1.0,
        "unique_question_rate": 1.0,
        "privacy_violation_rate": 0.0,
    }
