import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_TYPES = {
    "project",
    "decision",
    "responsibility",
    "impact",
    "retrospective",
    "job_gap",
}
PRIVATE_PATTERN = re.compile(
    r"姓名|电话|手机|邮箱|年龄|性别|婚育|住址|家庭|身份证"
)


def evaluate_question_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, object]] = []
    total_questions = 0
    linked_questions = 0
    unique_questions: set[str] = set()
    covered_types: set[str] = set()
    privacy_violations = 0
    for case in cases:
        case_types: set[str] = set()
        case_linked = 0
        questions = case.get("questions", [])
        for item in questions:
            question = str(item["question"]).strip()
            total_questions += 1
            normalized = re.sub(r"\s+", "", question).casefold()
            unique_questions.add(normalized)
            question_type = str(item["type"])
            case_types.add(question_type)
            covered_types.add(question_type)
            terms = [str(term) for term in item.get("evidence_terms", [])]
            linked = any(term in question for term in terms)
            linked_questions += int(linked)
            case_linked += int(linked)
            privacy_violations += int(bool(PRIVATE_PATTERN.search(question)))
        details.append(
            {
                "case_id": case["case_id"],
                "questions": len(questions),
                "evidence_link_rate": (
                    case_linked / len(questions) if questions else 0.0
                ),
                "covered_types": sorted(case_types),
            }
        )
    return {
        "summary": {
            "cases": len(cases),
            "questions": total_questions,
            "evidence_link_rate": (
                linked_questions / total_questions
                if total_questions
                else 0.0
            ),
            "type_coverage": len(covered_types & REQUIRED_TYPES)
            / len(REQUIRED_TYPES),
            "unique_question_rate": (
                len(unique_questions) / total_questions
                if total_questions
                else 0.0
            ),
            "privacy_violation_rate": (
                privacy_violations / total_questions
                if total_questions
                else 0.0
            ),
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate labelled resume-grounded interview questions."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/resume_interview_questions.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate_question_cases(cases)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
