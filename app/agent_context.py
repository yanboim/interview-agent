"""跨 Agent 传递的对话上下文。

多 Agent 模式下,Supervisor 通过 tool-calling 委派任务给专业 Agent。默认情况下
子 Agent 只会收到 Supervisor 拼装的 task 字符串,丢失全部对话历史(见 multi_agent
模块的 _invoke)。本模块用一个 ContextVar 在 Supervisor 的调用链里携带「已预算裁剪的
对话历史」,子 Agent 工具执行时可读取并注入,从而恢复多轮对话的上下文连续性。

ContextVar 在同一 asyncio task / 同步调用栈内自动传播,因此 Supervisor 的 ReAct
循环里发起的 tool_call 会继承该上下文,无需显式传参。
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
