"""把 Agent 输出转换为稳定文本、来源和声明级引用元数据。"""

import re
from typing import Any

from app.agent_contracts import CITATION_SCHEMA_VERSION


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
        r"证据ID：(?P<evidence_id>[^\n]+)\n"
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
                "evidence_id": match.group("evidence_id").strip(),
                "kind": "public",
                "url": match.group("url").strip(),
                "fetched_at": match.group("fetched_at").strip(),
                "snippet": match.group("snippet").strip()[:300],
            }
        )
    if tool_name == "search_interview_knowledge" or "来源：" in content:
        private_pattern = re.compile(
            r"证据ID：(?P<evidence_id>[^\n]+)\n"
            r"来源：(?P<label>[^\n]+)\n"
            r".*?^内容：(?P<snippet>.*?)(?=\n</untrusted_evidence>|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        for match in private_pattern.finditer(content):
            label = match.group("label").strip()
            if label:
                sources.append(
                    {
                        "evidence_id": match.group("evidence_id").strip(),
                        "label": label,
                        "kind": "private",
                        "snippet": match.group("snippet").strip()[:300],
                    }
                )
    unique: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for source in sources:
        key = (
            source["kind"],
            source.get("evidence_id", ""),
            source["label"],
            source.get("url", ""),
        )
        unique[key] = source
    return list(unique.values())


def build_citation_metadata(
    answer: str,
    sources: list[dict[str, str]],
) -> dict[str, object]:
    known = {
        source.get("evidence_id", "")
        for source in sources
        if source.get("evidence_id")
    }
    citations: list[dict[str, object]] = []
    unsupported_claims: list[str] = []
    for claim in re.split(r"(?<=[。！？.!?])\s+|\n+", answer):
        normalized = claim.strip()
        if not normalized:
            continue
        referenced = sorted(
            evidence_id
            for evidence_id in known
            if f"[{evidence_id}]" in normalized
            or f"【{evidence_id}】" in normalized
        )
        conflict = "[conflicting]" in normalized or "[证据冲突]" in normalized
        unsupported = "[unsupported]" in normalized or "[无证据]" in normalized
        if referenced or conflict or unsupported:
            support = (
                "conflicting"
                if conflict
                else "unsupported"
                if unsupported
                else "supported"
            )
            clean_claim = re.sub(r"\[(?:[^\]]+)\]|【[^】]+】", "", normalized).strip()
            citations.append(
                {
                    "claim": clean_claim or normalized,
                    "evidence_ids": referenced,
                    "support": support,
                }
            )
            if unsupported:
                unsupported_claims.append(clean_claim or normalized)
    return {
        "schema_version": CITATION_SCHEMA_VERSION,
        "citations": citations,
        "unsupported_claims": unsupported_claims,
    }
