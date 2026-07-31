import argparse
import json
from pathlib import Path
from typing import Any

from app.interview_review_engine import (
    InterviewReviewResult,
    TranscriptSegment,
    pair_confirmed_turns,
)


def evaluate_review_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    details = []
    pairing_success = 0
    schema_success = 0
    candidate_only = 0
    for case in cases:
        segments = [
            TranscriptSegment.model_validate(item)
            for item in case["segments"]
        ]
        paired = pair_confirmed_turns(segments)
        expected = case["expected_turns"]
        pairing_ok = paired == expected
        pairing_success += int(pairing_ok)
        try:
            result = InterviewReviewResult.model_validate(case["candidate"])
            schema_ok = len(result.turns) == len(expected)
        except ValueError:
            schema_ok = False
        schema_success += int(schema_ok)
        candidate_ok = all(
            turn["answer"] not in {
                segment.text
                for segment in segments
                if segment.speaker == "interviewer"
            }
            for turn in paired
        )
        candidate_only += int(candidate_ok)
        details.append(
            {
                "case_id": case["case_id"],
                "pairing_correct": pairing_ok,
                "schema_valid": schema_ok,
                "candidate_only": candidate_ok,
            }
        )
    count = len(cases)
    return {
        "summary": {
            "cases": count,
            "pairing_accuracy": pairing_success / count if count else 0.0,
            "schema_success_rate": schema_success / count if count else 0.0,
            "candidate_only_rate": candidate_only / count if count else 0.0,
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate synthetic real-interview review cases."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/interview_reviews.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate_review_cases(cases)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
