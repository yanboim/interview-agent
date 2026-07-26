from app.llm_reranker import parse_ranking


def test_parse_ranking_accepts_json_array():
    assert parse_ranking("[3, 1, 2]", 3) == [3, 1, 2]


def test_parse_ranking_removes_invalid_and_duplicate_indices():
    assert parse_ranking("结果：[2, 2, 9, 1]", 3) == [2, 1]


def test_parse_ranking_rejects_non_json_response():
    assert parse_ranking("候选 2 最相关", 3) == []
