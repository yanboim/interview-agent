"""RAG 检索评测命令入口；评测能力位于 ``app.rag_evaluation``。"""

import argparse
import json
from pathlib import Path

from app.rag_evaluation import evaluate, load_cases

__all__ = ["evaluate", "load_cases"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval against human-labelled chunk IDs."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/chunk_questions.jsonl"),
    )
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--lexical-rerank", action="store_true")
    parser.add_argument("--llm-rerank", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(
        load_cases(args.dataset),
        k=args.k,
        rerank=args.rerank,
        lexical_rerank=args.lexical_rerank,
        llm_rerank=args.llm_rerank,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
