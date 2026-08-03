"""Public-search provider adapter and untrusted evidence projection."""

from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from app.agent_safety import content_fingerprint, wrap_untrusted_evidence


def execute_public_web_search(
    clean_query: str,
    settings: object,
    *,
    post: Callable[..., Any] = httpx.post,
) -> str:
    response = post(
        settings.web_search_api_url,
        json={
            "api_key": settings.web_search_api_key,
            "query": clean_query,
            "max_results": settings.web_search_max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=settings.web_search_timeout_seconds,
    )
    response.raise_for_status()
    fetched_at = datetime.now(UTC).isoformat()
    results = []
    for item in response.json().get("results", []):
        url = str(item.get("url", "")).strip()
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        results.append({
            "title": str(item.get("title", "")).strip(),
            "url": url,
            "snippet": str(item.get("content", "")).strip()[:1200],
            "fetched_at": fetched_at,
        })
    if not results:
        return "公开网络未返回可引用结果。"
    return "\n\n".join(
        wrap_untrusted_evidence(
            f"[网络来源 {index}]\n"
            f"证据ID：web-{content_fingerprint(item['url'])[:24]}\n"
            f"标题：{item['title']}\n"
            f"链接：{item['url']}\n抓取时间：{item['fetched_at']}\n"
            f"摘要：{item['snippet']}",
            evidence_type="public_web",
            evidence_id=f"web-{content_fingerprint(item['url'])[:24]}",
        )
        for index, item in enumerate(results, start=1)
    )
