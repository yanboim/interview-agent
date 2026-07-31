"""会话历史 HTTP 适配器：所有查询和变更都限定为当前服务端用户。"""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    ConversationArchiveRequest,
    ConversationRenameRequest,
    ConversationSummary,
    HistoryMessage,
)
from app.api.security import resolve_user_id

router = APIRouter()


@router.get("/api/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    request: Request,
    user_id: str,
    include_archived: bool = False,
) -> list[dict[str, str | None]]:
    user_id = resolve_user_id(request, user_id)
    if not user_id or len(user_id) > 128:
        raise HTTPException(status_code=422, detail="user_id 不合法")
    return await run_sync(
        get_runtime().conversation_store.list_conversations,
        user_id,
        include_archived=include_archived,
    )


@router.post("/api/conversations/archive")
async def archive_conversations(
    payload: ConversationArchiveRequest,
    request: Request,
) -> dict[str, int]:
    user_id = resolve_user_id(request, payload.user_id)
    updated = await run_sync(
        get_runtime().conversation_store.archive_conversations,
        user_id=user_id,
        session_ids=payload.session_ids,
        archived=payload.archived,
    )
    return {"updated": updated}


@router.get(
    "/api/conversations/{session_id}/messages",
    response_model=list[HistoryMessage],
)
async def conversation_messages(
    request: Request,
    session_id: str,
    user_id: str,
) -> list[HistoryMessage]:
    user_id = resolve_user_id(request, user_id)
    messages = await run_sync(
        get_runtime().conversation_store.get_messages,
        user_id=user_id,
        session_id=session_id.strip(),
    )
    return [
        HistoryMessage(
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            metadata=message.metadata,
        )
        for message in messages
    ]


@router.delete("/api/conversations/{session_id}")
async def delete_conversation(
    request: Request,
    session_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_conversation,
        user_id=user_id,
        session_id=session_id.strip(),
    )
    return {"deleted": deleted}


@router.patch(
    "/api/conversations/{session_id}",
    response_model=ConversationSummary,
)
async def rename_conversation(
    request: Request,
    session_id: str,
    payload: ConversationRenameRequest,
) -> dict[str, str]:
    user_id = resolve_user_id(request, payload.user_id)
    renamed = await run_sync(
        get_runtime().conversation_store.rename_conversation,
        user_id=user_id,
        session_id=session_id.strip(),
        title=payload.title,
    )
    if not renamed:
        raise HTTPException(status_code=404, detail="会话不存在")
    return renamed
