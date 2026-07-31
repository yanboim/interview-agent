"""以供应商无关的保守预算裁剪聊天历史，并维护可持久化的早期对话摘要。"""

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


MESSAGE_FRAMING_TOKENS = 4


class ChatContextBudgetExceeded(ValueError):
    """The current user message cannot fit in the context window."""


@dataclass(frozen=True)
class ContextMessage:
    id: int
    role: str
    content: str


@dataclass(frozen=True)
class ChatContextPlan:
    history: tuple[dict[str, str], ...]
    summary: str
    summary_through_message_id: int | None
    estimated_tokens: int
    truncated_messages: int


def estimate_text_tokens(text: str) -> int:
    """用 UTF-8 字节数估算 token 上界，宁可少带历史也不突破模型窗口。"""
    return max(1, len(text.encode("utf-8")))


def estimate_message_tokens(role: str, content: str) -> int:
    return (
        MESSAGE_FRAMING_TOKENS
        + estimate_text_tokens(role)
        + estimate_text_tokens(content)
    )


def validate_current_message(content: str, token_budget: int) -> None:
    if token_budget <= 0:
        raise ValueError("chat context token budget must be positive")
    required = estimate_message_tokens("user", content)
    if required > token_budget:
        raise ChatContextBudgetExceeded(
            f"当前消息超过聊天上下文预算：{required}>{token_budget} tokens"
        )


def _normalized_excerpt(content: str, *, byte_limit: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", content).strip()
    if len(normalized.encode("utf-8")) <= byte_limit:
        return normalized
    output: list[str] = []
    size = 0
    for character in normalized:
        width = len(character.encode("utf-8"))
        if size + width > byte_limit - len("…".encode("utf-8")):
            break
        output.append(character)
        size += width
    return "".join(output).rstrip() + "…"


def _tail_within_token_budget(text: str, token_budget: int) -> str:
    if token_budget <= 0:
        return ""
    if estimate_text_tokens(text) <= token_budget:
        return text
    ellipsis = "…"
    remaining = max(0, token_budget - len(ellipsis.encode("utf-8")))
    output: list[str] = []
    size = 0
    for character in reversed(text):
        width = len(character.encode("utf-8"))
        if size + width > remaining:
            break
        output.append(character)
        size += width
    return ellipsis + "".join(reversed(output)).lstrip()


def _merge_summary(
    existing_summary: str,
    folded: Iterable[ContextMessage],
    *,
    through_message_id: int,
    token_budget: int,
) -> str:
    folded_list = list(folded)
    digest = hashlib.sha256()
    if existing_summary:
        digest.update(existing_summary.encode("utf-8"))
    for message in folded_list:
        digest.update(str(message.id).encode("ascii"))
        digest.update(b"\0")
        digest.update(message.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(message.content.encode("utf-8"))

    labels = {"user": "用户", "assistant": "助手"}
    additions = [
        f"{labels.get(message.role, message.role)}："
        f"{_normalized_excerpt(message.content)}"
        for message in folded_list
    ]
    body_parts = [part for part in (existing_summary, *additions) if part]
    header = (
        f"较早对话摘要（截至消息 {through_message_id}，"
        f"指纹 {digest.hexdigest()[:12]}）："
    )
    body_budget = max(
        0,
        token_budget - estimate_text_tokens(header + "\n"),
    )
    body = _tail_within_token_budget("\n".join(body_parts), body_budget)
    return _tail_within_token_budget(
        f"{header}\n{body}".rstrip(),
        token_budget,
    )


def plan_chat_context(
    messages: Iterable[ContextMessage],
    *,
    current_content: str,
    existing_summary: str = "",
    summary_through_message_id: int | None = None,
    token_budget: int,
    summary_token_budget: int,
) -> ChatContextPlan:
    validate_current_message(current_content, token_budget)
    if summary_token_budget <= 0:
        raise ValueError("chat summary token budget must be positive")
    if summary_token_budget >= token_budget:
        raise ValueError(
            "chat summary token budget must be smaller than context budget"
        )

    candidates = tuple(
        message
        for message in messages
        if (
            summary_through_message_id is None
            or message.id > summary_through_message_id
        )
    )
    current_tokens = estimate_message_tokens("user", current_content)
    existing_history: list[dict[str, str]] = []
    if existing_summary:
        existing_history.append(
            {"role": "system", "content": existing_summary}
        )
    existing_history.extend(
        {"role": message.role, "content": message.content}
        for message in candidates
    )
    existing_total = current_tokens + sum(
        estimate_message_tokens(item["role"], item["content"])
        for item in existing_history
    )
    if existing_total <= token_budget:
        return ChatContextPlan(
            history=tuple(existing_history),
            summary=existing_summary,
            summary_through_message_id=summary_through_message_id,
            estimated_tokens=existing_total,
            truncated_messages=0,
        )

    reserved_summary_tokens = min(
        (
            summary_token_budget
            + MESSAGE_FRAMING_TOKENS
            + estimate_text_tokens("system")
        ),
        max(0, token_budget - current_tokens),
    )
    recent_budget = max(
        0,
        token_budget - current_tokens - reserved_summary_tokens,
    )
    # 从最近消息向前装箱，优先保留当前对话连续性。
    retained_reversed: list[ContextMessage] = []
    retained_tokens = 0
    for message in reversed(candidates):
        message_tokens = estimate_message_tokens(
            message.role,
            message.content,
        )
        if retained_tokens + message_tokens > recent_budget:
            break
        retained_reversed.append(message)
        retained_tokens += message_tokens
    retained = tuple(reversed(retained_reversed))
    folded_count = len(candidates) - len(retained)
    # 不让窗口从孤立的 assistant 回答开始，避免模型缺少对应用户问题。
    if retained and retained[0].role == "assistant":
        retained = retained[1:]
        folded_count += 1
    folded = candidates[:folded_count]

    summary = existing_summary
    through = summary_through_message_id
    if folded:
        through = folded[-1].id
        summary = _merge_summary(
            existing_summary,
            folded,
            through_message_id=through,
            token_budget=summary_token_budget,
        )
    elif summary:
        summary = _tail_within_token_budget(summary, summary_token_budget)

    context_summary = summary
    history: list[dict[str, str]] = []
    if context_summary:
        history.append({"role": "system", "content": context_summary})
    history.extend(
        {"role": message.role, "content": message.content}
        for message in retained
    )
    estimated_tokens = current_tokens + sum(
        estimate_message_tokens(item["role"], item["content"])
        for item in history
    )
    while retained and estimated_tokens > token_budget:
        retained = retained[1:]
        history = (
            (
                [{"role": "system", "content": context_summary}]
                if context_summary
                else []
            )
            + [
                {"role": message.role, "content": message.content}
                for message in retained
            ]
        )
        estimated_tokens = current_tokens + sum(
            estimate_message_tokens(item["role"], item["content"])
            for item in history
        )

    if estimated_tokens > token_budget and context_summary:
        available = max(
            0,
            token_budget
            - current_tokens
            - MESSAGE_FRAMING_TOKENS
            - estimate_text_tokens("system"),
        )
        context_summary = _tail_within_token_budget(
            context_summary,
            available,
        )
        history = (
            [{"role": "system", "content": context_summary}]
            if context_summary
            else []
        )
        estimated_tokens = current_tokens + sum(
            estimate_message_tokens(item["role"], item["content"])
            for item in history
        )

    return ChatContextPlan(
        history=tuple(history),
        summary=summary,
        summary_through_message_id=through,
        estimated_tokens=estimated_tokens,
        truncated_messages=folded_count,
    )
