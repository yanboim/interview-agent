import re
from typing import Any


def extract_message_text(message: Any) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                texts.append(str(block["text"]))
        return "\n".join(texts)
    return str(content)


def extract_sources(tool_name: str, content: str) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    web_pattern = re.compile(
        r"标题：(?P<label>[^\n]+)\n"
        r"链接：(?P<url>[^\n]+)\n"
        r"抓取时间：(?P<fetched_at>[^\n]+)\n"
        r"摘要：(?P<snippet>.*?)(?=\n\n\[网络来源|\Z)",
        re.DOTALL,
    )
    for match in web_pattern.finditer(content):
        sources.append(
            {
                "label": match.group("label").strip(),
                "kind": "public",
                "url": match.group("url").strip(),
                "fetched_at": match.group("fetched_at").strip(),
                "snippet": match.group("snippet").strip()[:300],
            }
        )
    if tool_name == "search_interview_knowledge" or "来源：" in content:
        for label in re.findall(r"^来源：(.+)$", content, re.MULTILINE):
            clean_label = label.strip()
            if clean_label:
                content_match = re.search(
                    rf"^来源：{re.escape(clean_label)}$\n.*?^内容：(.*?)(?=\n\n\[资料|\Z)",
                    content,
                    re.MULTILINE | re.DOTALL,
                )
                source = {"label": clean_label, "kind": "private"}
                if content_match:
                    source["snippet"] = content_match.group(1).strip()[:300]
                sources.append(source)
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for source in sources:
        key = (
            source["kind"],
            source["label"],
            source.get("url", ""),
        )
        unique[key] = source
    return list(unique.values())
