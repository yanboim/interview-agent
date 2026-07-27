import asyncio
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.api.agent_io import extract_message_text, extract_sources
from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import ChatRequest, ChatResponse
from app.api.security import resolve_user_id
from app.application.chat_service import ChatTurnConflict
from app.chat_context import ChatContextBudgetExceeded
from app.operations import request_metrics
from app.tool_context import reset_tool_identity, set_tool_identity

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> ChatResponse:
    runtime = get_runtime()
    user_id = resolve_user_id(http_request, request.user_id)
    try:
        claim = await run_sync(
            runtime.chat_turn_service.begin,
            user_id=user_id,
            session_id=request.session_id,
            content=request.message,
            idempotency_key=idempotency_key,
        )
    except ChatContextBudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ChatTurnConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        ) from exc
    if claim["outcome"] == "completed":
        return ChatResponse(
            user_id=user_id,
            session_id=request.session_id,
            turn_id=str(claim["turn_id"]),
            answer=str(claim["answer"]),
        )

    current_user = getattr(http_request.state, "current_user", None)
    identity_token = set_tool_identity(
        user_id, current_user.role if current_user else "user"
    )
    answer = ""
    try:
        with request_metrics.dependency("glm"):
            result = await runtime.get_interview_agent().ainvoke(
                {"messages": claim["messages"]}
            )
        answer = extract_message_text(result["messages"][-1])
        sources: list[dict[str, str]] = []
        for result_message in result["messages"]:
            if not isinstance(result_message, ToolMessage):
                continue
            sources.extend(
                extract_sources(
                    str(getattr(result_message, "name", "") or ""),
                    extract_message_text(result_message),
                )
            )
        source_map = {
            (source["kind"], source["label"], source.get("url", "")): source
            for source in sources
        }
        metadata_payload = {
            "knowledge_used": any(
                source["kind"] == "private" for source in source_map.values()
            ),
            "sources": list(source_map.values()),
        }
        await run_sync(
            runtime.chat_turn_service.complete,
            claim,
            user_id=user_id,
            session_id=request.session_id,
            answer=answer,
            metadata=metadata_payload if source_map else {},
        )
        return ChatResponse(
            user_id=user_id,
            session_id=request.session_id,
            turn_id=str(claim["turn_id"]),
            answer=answer,
        )
    except Exception as exc:
        await run_sync(
            runtime.chat_turn_service.fail,
            claim,
            partial_answer=answer,
            error=f"{type(exc).__name__}: {exc}",
        )
        logger.exception("Agent execution failed for session %s", request.session_id)
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{exc}") from exc
    finally:
        reset_tool_identity(identity_token)


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> StreamingResponse:
    runtime = get_runtime()
    user_id = resolve_user_id(http_request, request.user_id)
    try:
        claim = await run_sync(
            runtime.chat_turn_service.begin,
            user_id=user_id,
            session_id=request.session_id,
            content=request.message,
            idempotency_key=idempotency_key,
        )
    except ChatContextBudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ChatTurnConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        ) from exc

    async def generate():
        if claim["outcome"] == "completed":
            answer = str(claim["answer"])
            metadata = dict(claim["metadata"])  # type: ignore[arg-type]
            if answer:
                yield json.dumps(
                    {"type": "token", "content": answer}, ensure_ascii=False
                ) + "\n"
            if metadata:
                yield json.dumps(
                    {"type": "sources", **metadata}, ensure_ascii=False
                ) + "\n"
            yield json.dumps(
                {
                    "type": "done",
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": True,
                },
                ensure_ascii=False,
            ) + "\n"
            return

        answer_parts: list[str] = []
        source_map: dict[tuple[str, str, str], dict[str, str]] = {}
        knowledge_used = False
        current_user = getattr(http_request.state, "current_user", None)
        identity_token = set_tool_identity(
            user_id, current_user.role if current_user else "user"
        )
        try:
            with request_metrics.dependency("glm"):
                async for message, _ in runtime.get_interview_agent().astream(
                    {"messages": claim["messages"]},
                    stream_mode="messages",
                ):
                    if isinstance(message, ToolMessage):
                        tool_name = str(getattr(message, "name", "") or "")
                        tool_content = extract_message_text(message)
                        for source in extract_sources(tool_name, tool_content):
                            key = (
                                source["kind"],
                                source["label"],
                                source.get("url", ""),
                            )
                            source_map[key] = source
                            knowledge_used = (
                                knowledge_used or source["kind"] == "private"
                            )
                        continue
                    if not isinstance(message, AIMessageChunk):
                        continue
                    text = extract_message_text(message)
                    if not text:
                        continue
                    answer_parts.append(text)
                    yield json.dumps(
                        {"type": "token", "content": text}, ensure_ascii=False
                    ) + "\n"

            answer = "".join(answer_parts) or "Agent 没有返回文本内容。"
            metadata_payload = {
                "knowledge_used": knowledge_used,
                "sources": list(source_map.values()),
            }
            if knowledge_used or source_map:
                yield json.dumps(
                    {"type": "sources", **metadata_payload}, ensure_ascii=False
                ) + "\n"
            await run_sync(
                runtime.chat_turn_service.complete,
                claim,
                user_id=user_id,
                session_id=request.session_id,
                answer=answer,
                metadata=metadata_payload if source_map else {},
            )
            yield json.dumps(
                {
                    "type": "done",
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": False,
                },
                ensure_ascii=False,
            ) + "\n"
        except (asyncio.CancelledError, GeneratorExit):
            runtime.chat_turn_service.cancel(
                claim, partial_answer="".join(answer_parts)
            )
            raise
        except Exception as exc:
            await run_sync(
                runtime.chat_turn_service.fail,
                claim,
                partial_answer="".join(answer_parts),
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception(
                "Streaming agent execution failed for session %s",
                request.session_id,
            )
            yield json.dumps(
                {"type": "error", "detail": f"Agent 执行失败：{exc}"},
                ensure_ascii=False,
            ) + "\n"
        finally:
            reset_tool_identity(identity_token)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
