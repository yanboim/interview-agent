import json
from pathlib import Path

from scripts.evaluate_interview_reviews import evaluate_review_cases


def test_interview_review_fixture_meets_baseline() -> None:
    cases = [
        json.loads(line)
        for line in Path("eval/interview_reviews.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    assert evaluate_review_cases(cases)["summary"] == {
        "cases": 1,
        "pairing_accuracy": 1.0,
        "schema_success_rate": 1.0,
        "candidate_only_rate": 1.0,
    }
