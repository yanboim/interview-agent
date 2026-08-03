"""评估简历评估结果的覆盖度与事实一致性。"""

import argparse
import json
from pathlib import Path
from typing import Any

from app.resume_engine import ResumeAnalysisResult, find_fact_warnings


def _recall(actual: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(actual & expected) / len(expected)


def evaluate_resume_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, object]] = []
    schema_success = 0
    gap_recall = 0.0
    issue_recall = 0.0
    fact_guard_success = 0
    for case in cases:
        try:
            result = ResumeAnalysisResult.model_validate(case["candidate"])
        except (KeyError, ValueError) as exc:
            details.append(
                {
                    "case_id": case.get("case_id", "unknown"),
                    "schema_valid": False,
                    "error": str(exc),
                }
            )
            continue
        schema_success += 1
        gaps = _recall(
            set(result.keyword_gaps),
            set(case.get("expected_keyword_gaps", [])),
        )
        categories = _recall(
            {issue.category for issue in result.issues},
            set(case.get("expected_issue_categories", [])),
        )
        warnings = find_fact_warnings(case["resume_text"], result.draft)
        warning_expected = bool(case.get("expect_fact_warning", False))
        guard_passed = bool(warnings) == warning_expected
        fact_guard_success += int(guard_passed)
        gap_recall += gaps
        issue_recall += categories
        details.append(
            {
                "case_id": case["case_id"],
                "schema_valid": True,
                "keyword_gap_recall": gaps,
                "issue_category_recall": categories,
                "fact_guard_passed": guard_passed,
                "fact_warnings": warnings,
            }
        )
    count = len(cases)
    return {
        "summary": {
            "cases": count,
            "schema_success_rate": schema_success / count if count else 0.0,
            "keyword_gap_recall": gap_recall / count if count else 0.0,
            "issue_category_recall": issue_recall / count if count else 0.0,
            "fact_guard_success_rate": (
                fact_guard_success / count if count else 0.0
            ),
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate labelled resume-analysis outputs without live calls."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/resume_analysis.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate_resume_cases(cases)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
