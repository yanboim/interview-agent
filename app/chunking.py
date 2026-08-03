"""按 Markdown 标题语义切分知识文档，并为每块保留可检索的标题上下文。"""

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


_MARKDOWN_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def heading_context_at(content: str, position: int) -> list[str]:
    """返回文档中给定位置之前最近的一组（多级）Markdown 标题。

    用层级字典记录各 ``#`` 层级最近标题，遇到更高级标题时清除其下
    子层级，从而还原到 ``position`` 处仍生效的标题路径。

    参数:
        content: 原始文档全文。
        position: 正文中的字符偏移，只考虑该位置之前的标题。

    返回:
        从最高级到当前级的标题列表，按层级升序排列；无标题时为空。
    """
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
    """保留分块原边界，并为每块注入继承自上层 Markdown 标题的检索上下文。

    先用按标题与中文标点递归切分的分割器得到原始分块，再逐块定位其在
    原文中的位置，取出继承标题路径作为 ``heading_context``。该上下文
    会前缀到分块正文（``[检索上下文] ...``），提升检索命中率，同时把
    去前缀的稳定正文存入 ``_stable_content`` 供 ``stable_chunk_id`` 使用。

    参数:
        documents: 待切分的知识文档列表。
        chunk_size: 单块最大字符数。
        chunk_overlap: 相邻块重叠字符数，避免在句中切断丢失语义。

    返回:
        注入了 ``heading_context`` 与 ``_stable_content`` 元数据的分块列表。
    """
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
