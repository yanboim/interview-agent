from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolIdentity:
    user_id: str
    role: str
    request_id: str = ""
    interaction_type: str = ""
    interaction_id: str = ""


_identity: ContextVar[ToolIdentity] = ContextVar(
    "tool_identity",
    default=ToolIdentity(user_id="anonymous", role="user"),
)


def get_tool_identity() -> ToolIdentity:
    return _identity.get()


def set_tool_identity(
    user_id: str,
    role: str,
    *,
    request_id: str = "",
    interaction_type: str = "",
    interaction_id: str = "",
) -> Token[ToolIdentity]:
    return _identity.set(
        ToolIdentity(
            user_id=user_id,
            role=role,
            request_id=request_id,
            interaction_type=interaction_type,
            interaction_id=interaction_id,
        )
    )


def reset_tool_identity(token: Token[ToolIdentity]) -> None:
    _identity.reset(token)
