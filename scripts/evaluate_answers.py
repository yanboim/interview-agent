import argparse
import json
from pathlib import Path
from typing import Any

from app.evaluation import citation_scores, claim_support_rate


def evaluate_answer_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    details = []
    precision = 0.0
    recall = 0.0
    faithfulness = 0.0
    for case in cases:
        citations = citation_scores(
            case.get("citations", []),
            set(case.get("relevant_sources", [])),
        )
        supported = claim_support_rate(case.get("supported_claims", []))
        precision += citations["citation_precision"]
        recall += citations["citation_recall"]
        faithfulness += supported
        details.append(
            {
                "question": case["question"],
                **citations,
                "faithfulness": supported,
            }
        )
    count = len(cases)
    return {
        "summary": {
            "cases": count,
            "citation_precision": precision / count if count else 0.0,
            "citation_recall": recall / count if count else 0.0,
            "faithfulness": faithfulness / count if count else 0.0,
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate answer citations and human-labelled claim support."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/answer_quality.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate_answer_cases(cases)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
