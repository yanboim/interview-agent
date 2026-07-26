from langchain_core.documents import Document

from app.chunking import heading_context_at, split_with_heading_context


def test_heading_context_tracks_markdown_hierarchy():
    content = "# Java\n\n## JVM\n\n### G1\n\n工作原理"

    assert heading_context_at(content, content.index("工作原理")) == [
        "Java",
        "JVM",
        "G1",
    ]


def test_heading_context_drops_previous_child_heading():
    content = "# Java\n\n## JVM\n\n### G1\n正文\n\n## 并发\n\nvolatile"

    assert heading_context_at(content, content.index("volatile")) == [
        "Java",
        "并发",
    ]


def test_splitter_inherits_headings_without_changing_stable_content():
    document = Document(
        page_content=(
            "# Spring Boot\n\n## 题库\n\n### 自动配置原理\n\n"
            + "自动配置内容。" * 30
        ),
        metadata={"source": "knowledge/spring.md"},
    )

    chunks = split_with_heading_context(
        [document],
        chunk_size=100,
        chunk_overlap=10,
    )

    topic_chunks = [
        chunk
        for chunk in chunks
        if "自动配置内容" in chunk.page_content
    ]
    assert topic_chunks
    assert all(
        chunk.metadata["heading_context"]
        == "Spring Boot > 题库 > 自动配置原理"
        for chunk in topic_chunks
    )
    assert all(
        chunk.page_content.startswith(
            "[检索上下文] Spring Boot > 题库 > 自动配置原理"
        )
        for chunk in topic_chunks
    )
    assert all(
        "[检索上下文]" not in chunk.metadata["_stable_content"]
        for chunk in topic_chunks
    )
