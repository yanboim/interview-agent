"""跨 Agent 传递的对话上下文。

多 Agent 模式下，Workflow V2 直接调用一个或多个专业 Agent。本模块用 ContextVar
携带「已预算裁剪的对话 + 不可变个性化快照」，每条显式专家分支据此构造同一版本的
DelegationEnvelope，而不复制完整历史。

ContextVar 会复制到 asyncio 子任务，因此并发专家分支可透明访问同一请求快照。
请求结束后由应用用例 reset，避免跨请求泄漏。
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass

from app.agent_context_service import AgentContextSnapshotV1


@dataclass(frozen=True)
class ConversationContext:
    """已预算裁剪的对话历史,供子 Agent 继承。

    messages 结构与 LangChain 的 messages 列表一致,每项为 {"role", "content"}。
    """

    messages: tuple[dict[str, str], ...]
    snapshot: AgentContextSnapshotV1 | None = None


_EMPTY = ConversationContext(messages=(), snapshot=None)

_conversation: ContextVar[ConversationContext] = ContextVar(
    "agent_conversation_context",
    default=_EMPTY,
)


def get_conversation_context() -> ConversationContext:
    """返回当前调用链上的对话上下文(无则返回空)。"""
    return _conversation.get()


def set_conversation_context(
    messages: list[dict[str, str]],
    snapshot: AgentContextSnapshotV1 | None = None,
) -> Token[ConversationContext]:
    """设置对话上下文,返回用于 reset 的 token。"""
    return _conversation.set(
        ConversationContext(messages=tuple(messages), snapshot=snapshot)
    )


def reset_conversation_context(token: Token[ConversationContext]) -> None:
    """恢复到 set 之前的上下文状态。"""
    _conversation.reset(token)
