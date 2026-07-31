import json
from pathlib import Path

from scripts.evaluate_resumes import evaluate_resume_cases


def test_resume_evaluation_fixture_passes_quality_guards() -> None:
    dataset = Path("eval/resume_analysis.jsonl")
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    report = evaluate_resume_cases(cases)

    assert report["summary"] == {
        "cases": 3,
        "schema_success_rate": 1.0,
        "keyword_gap_recall": 1.0,
        "issue_category_recall": 1.0,
        "fact_guard_success_rate": 1.0,
    }
