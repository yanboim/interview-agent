"""评估指标聚合报告的测试。"""

from app.evaluation import hit_at_k, reciprocal_rank


def test_retrieval_metrics() -> None:
    retrieved = ["wrong.md", "correct.md", "other.md"]
    relevant = {"correct.md"}

    assert hit_at_k(retrieved, relevant) is True
    assert reciprocal_rank(retrieved, relevant) == 0.5


def test_retrieval_metrics_when_not_found() -> None:
    assert hit_at_k(["wrong.md"], {"correct.md"}) is False
    assert reciprocal_rank(["wrong.md"], {"correct.md"}) == 0.0
