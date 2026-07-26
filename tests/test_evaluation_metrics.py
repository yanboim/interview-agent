from app.evaluation import (
    citation_scores,
    claim_support_rate,
    ndcg_at_k,
)
from scripts.evaluate_answers import evaluate_answer_cases


def test_ndcg_rewards_relevant_items_near_the_top():
    relevant = {"a", "b"}
    assert ndcg_at_k(["a", "x", "b"], relevant, 3) > ndcg_at_k(
        ["x", "a", "b"],
        relevant,
        3,
    )
    assert ndcg_at_k([], relevant, 3) == 0.0


def test_citation_and_faithfulness_metrics():
    scores = citation_scores(["rag.md", "wrong.md"], {"rag.md"})
    assert scores == {
        "citation_precision": 0.5,
        "citation_recall": 1.0,
    }
    assert claim_support_rate([True, True, False]) == 2 / 3


def test_answer_evaluation_report_has_stable_summary():
    report = evaluate_answer_cases(
        [
            {
                "question": "RAG",
                "citations": ["rag.md"],
                "relevant_sources": ["rag.md"],
                "supported_claims": [True, False],
            }
        ]
    )
    assert report["summary"] == {
        "cases": 1,
        "citation_precision": 1.0,
        "citation_recall": 1.0,
        "faithfulness": 0.5,
    }
