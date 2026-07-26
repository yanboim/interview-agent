from langchain_core.documents import Document

from app.lexical_reranker import (
    lexical_relevance,
    lexical_rerank_documents,
    lexical_units,
)


def test_lexical_units_supports_chinese_and_technical_tokens():
    units = lexical_units("Spring Boot 自动配置如何工作？")

    assert {"spring", "boot", "自动", "配置"}.issubset(units)
    assert "如何" not in units


def test_heading_match_gets_more_weight():
    query = "Spring Boot 自动配置"
    heading_match = "### Spring Boot 自动配置\n条件化装配 Bean"
    body_only_match = "### 启动流程\n稍后讨论 Spring Boot 自动配置"

    assert lexical_relevance(query, heading_match) > lexical_relevance(
        query, body_only_match
    )


def test_lexical_reranker_can_promote_better_heading():
    candidates = [
        (Document(page_content="### 启动流程\n自动配置是后续步骤"), 1.0),
        (Document(page_content="### 自动配置原理\n条件注解与 Bean"), 0.2),
    ]

    ranked = lexical_rerank_documents("自动配置原理", candidates)

    assert ranked[0][0].page_content.startswith("### 自动配置原理")
