"""按 Markdown 标题语义切分知识文档，并为每块保留可检索的标题上下文。"""

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


_MARKDOWN_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def heading_context_at(content: str, position: int) -> list[str]:
    hierarchy: dict[int, str] = {}
    for match in _MARKDOWN_HEADING.finditer(content):
        if match.start() > position:
            break
        level = len(match.group(1))
        hierarchy[level] = match.group(2).strip()
        for child_level in range(level + 1, 4):
            hierarchy.pop(child_level, None)
    return [hierarchy[level] for level in sorted(hierarchy)]


def split_with_heading_context(
    documents: list[Document],
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[Document]:
    """Keep existing chunk boundaries while adding inherited Markdown headings."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n# ",
            "\n## ",
            "\n### ",
            "\n\n",
            "\n",
            "。",
            "；",
            "，",
            " ",
        ],
    )
    contextual_chunks: list[Document] = []
    for document in documents:
        content = document.page_content
        search_from = 0
        for chunk in splitter.split_documents([document]):
            raw_content = chunk.page_content
            position = content.find(
                raw_content,
                max(0, search_from - chunk_overlap * 2),
            )
            if position < 0:
                position = content.find(raw_content)
            if position < 0:
                position = search_from

            headings = heading_context_at(content, position)
            context = " > ".join(headings)
            chunk.metadata["heading_context"] = context
            chunk.metadata["_stable_content"] = raw_content
            if context:
                chunk.page_content = (
                    f"[检索上下文] {context}\n\n{raw_content}"
                )
            contextual_chunks.append(chunk)
            search_from = max(search_from, position + len(raw_content))
    return contextual_chunks
