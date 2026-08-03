"""用户目标、头像、提醒偏好和今日训练建议的 HTTP 适配器。"""

import asyncio
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    CoachingMemoryCreateRequest,
    CoachingMemoryUpdateRequest,
    ProfileAvatarRequest,
    ProductEventRequest,
    ReminderPreferencesRequest,
    UserProfileRequest,
)
from app.api.security import resolve_user_id

router = APIRouter()


@router.get("/api/coaching-memories")
async def coaching_memories(
    request: Request,
    user_id: str,
) -> list[dict[str, object]]:
    """列出当前用户的长期训练记忆（所有者范围）。"""
    user_id = resolve_user_id(request, user_id)
    return await run_sync(
        get_runtime().conversation_store.list_coaching_memories,
        user_id=user_id,
    )


@router.post("/api/coaching-memories", status_code=201)
async def propose_coaching_memory(
    payload: CoachingMemoryCreateRequest,
    request: Request,
) -> dict[str, object]:
    """提议一条长期训练记忆（初始为 proposed，需用户确认后生效）。"""
    user_id = resolve_user_id(request, payload.user_id)
    return await run_sync(
        get_runtime().conversation_store.create_coaching_memory,
        user_id=user_id,
        kind=payload.kind,
        content=payload.content,
    )


@router.patch("/api/coaching-memories/{memory_id}")
async def update_coaching_memory(
    memory_id: str,
    payload: CoachingMemoryUpdateRequest,
    request: Request,
) -> dict[str, object]:
    """确认/纠正/拒绝一条记忆（所有者范围）。

    规则:
        纠正会把记忆退回 ``proposed``，需所有者再次确认才会进入生效上下文。
    """
    user_id = resolve_user_id(request, payload.user_id)
    try:
        memory = await run_sync(
            get_runtime().conversation_store.update_coaching_memory,
            user_id=user_id,
            memory_id=memory_id,
            action=payload.action,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


@router.delete("/api/coaching-memories/{memory_id}", status_code=204)
async def delete_coaching_memory(
    memory_id: str,
    request: Request,
    user_id: str,
) -> None:
    """删除一条长期训练记忆（所有者范围）。"""
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_coaching_memory,
        user_id=user_id,
        memory_id=memory_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="记忆不存在")


@router.get("/api/profile")
async def user_profile(request: Request, user_id: str) -> dict[str, object]:
    """返回当前用户的档案，无档案时返回默认值（所有者范围）。"""
    user_id = resolve_user_id(request, user_id)
    profile = await run_sync(
        get_runtime().conversation_store.get_user_profile,
        user_id=user_id,
    )
    return profile or {
        "user_id": user_id,
        "target_role": "",
        "experience_level": "高级",
        "focus_areas": "",
        "interview_date": None,
        "job_description": "",
        "avatar_data_url": None,
        "created_at": None,
        "updated_at": None,
    }


@router.put("/api/profile")
async def update_user_profile(
    payload: UserProfileRequest,
    request: Request,
) -> dict[str, object]:
    """更新或创建用户档案（目标岗位、经验、方向、面试日期、JD）。"""
    user_id = resolve_user_id(request, payload.user_id)
    return await run_sync(
        get_runtime().conversation_store.upsert_user_profile,
        user_id=user_id,
        target_role=payload.target_role,
        experience_level=payload.experience_level,
        focus_areas=payload.focus_areas,
        interview_date=payload.interview_date,
        job_description=payload.job_description,
    )


@router.put("/api/profile/avatar")
async def update_profile_avatar(
    payload: ProfileAvatarRequest,
    request: Request,
) -> dict[str, object]:
    """更新当前用户的头像（data URL，所有者范围）。"""
    user_id = resolve_user_id(request, payload.user_id)
    profile = await run_sync(
        get_runtime().conversation_store.update_profile_avatar,
        user_id=user_id,
        avatar_data_url=payload.avatar_data_url,
    )
    return {"avatar_data_url": profile["avatar_data_url"]}


@router.get("/api/reminders/preferences")
async def reminder_preferences(
    request: Request,
    user_id: str,
) -> dict[str, object]:
    """返回当前用户的提醒偏好（启用、时间、时区，所有者范围）。"""
    user_id = resolve_user_id(request, user_id)
    profile = await run_sync(
        get_runtime().conversation_store.get_user_profile,
        user_id=user_id,
    )
    return {
        "enabled": bool(profile and profile.get("reminder_enabled")),
        "reminder_time": str(profile.get("reminder_time")) if profile else "09:00",
        "timezone": str(profile.get("reminder_timezone")) if profile else "UTC",
    }


@router.put("/api/reminders/preferences")
async def update_reminder_preferences(
    payload: ReminderPreferencesRequest,
    request: Request,
) -> dict[str, object]:
    """更新提醒偏好（启用、时间、时区），校验 IANA 时区合法性。"""
    user_id = resolve_user_id(request, payload.user_id)
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="无效的 IANA 时区") from exc
    profile = await run_sync(
        get_runtime().conversation_store.update_reminder_preferences,
        user_id=user_id,
        enabled=payload.enabled,
        reminder_time=payload.reminder_time,
        timezone=payload.timezone,
    )
    return {
        "enabled": bool(profile["reminder_enabled"]),
        "reminder_time": profile["reminder_time"],
        "timezone": profile["reminder_timezone"],
    }


@router.get("/api/reminders/due")
async def due_reminders(request: Request, user_id: str) -> dict[str, object]:
    """按用户本地时间计算当前到期的复习提醒（所有者范围）。"""
    user_id = resolve_user_id(request, user_id)
    store = get_runtime().conversation_store
    profile, tasks = await asyncio.gather(
        run_sync(store.get_user_profile, user_id=user_id),
        run_sync(store.list_learning_tasks, user_id=user_id),
    )
    if not profile or not profile.get("reminder_enabled"):
        return {"due": False, "items": []}
    timezone = ZoneInfo(str(profile.get("reminder_timezone") or "UTC"))
    now = datetime.now(UTC).astimezone(timezone)
    reminder_time = str(profile.get("reminder_time") or "09:00")
    time_reached = now.strftime("%H:%M") >= reminder_time
    due_items = [
        {
            "type": "learning_task",
            "id": task["task_id"],
            "title": task["weakness"],
            "action": task["action"],
        }
        for task in tasks
        if task["status"] != "completed"
        and datetime.fromisoformat(str(task["due_at"])).astimezone(timezone) <= now
    ]
    return {
        "due": bool(time_reached and due_items),
        "items": due_items if time_reached else [],
        "local_date": now.date().isoformat(),
    }


@router.get("/api/today-plan")
async def today_plan(request: Request, user_id: str) -> dict[str, object]:
    """生成今日训练建议（优先继续面试，其次到期复习，最后新训练）。"""
    user_id = resolve_user_id(request, user_id)
    store = get_runtime().conversation_store
    profile, tasks, interview_rows, interviews_list = await asyncio.gather(
        run_sync(store.get_user_profile, user_id=user_id),
        run_sync(store.list_learning_tasks, user_id=user_id),
        run_sync(store.get_capability_rows, user_id=user_id),
        run_sync(store.list_interviews, user_id=user_id),
    )
    active = next(
        (item for item in interviews_list if item["status"] == "active"),
        None,
    )
    now = datetime.now(UTC)
    due_tasks = [
        task
        for task in tasks
        if task["status"] != "completed"
        and datetime.fromisoformat(str(task["due_at"])) <= now
    ]
    weakness_counts: dict[str, int] = {}
    for row in interview_rows:
        for weakness in json.loads(str(row.get("weaknesses_json") or "[]")):
            label = str(weakness)
            weakness_counts[label] = weakness_counts.get(label, 0) + 1
    top_weakness = (
        max(weakness_counts, key=weakness_counts.get) if weakness_counts else ""
    )
    target = str((profile or {}).get("target_role") or "")
    focus = str((profile or {}).get("focus_areas") or target)
    if active:
        recommendation = {
            "type": "resume_interview",
            "title": f"继续 {active['topic']} 模拟面试",
            "reason": "完成进行中的训练，避免上下文中断。",
            "href": f"/interviews/{active['interview_id']}",
        }
    elif due_tasks:
        recommendation = {
            "type": "review",
            "title": f"复习：{due_tasks[0]['weakness']}",
            "reason": "该任务已到复习时间，优先巩固遗忘风险最高的内容。",
            "href": "/learning",
        }
    else:
        recommendation = {
            "type": "new_interview",
            "title": f"训练 {focus or '目标岗位核心能力'}",
            "reason": (
                f"结合高频薄弱点“{top_weakness}”生成针对性问题。"
                if top_weakness
                else f"依据 {target or '你的目标岗位'} 与 JD 生成首轮基线训练。"
            ),
            "href": "/interviews",
        }
    return {
        "recommendation": recommendation,
        "top_weakness": top_weakness or None,
        "target_role": target or None,
        "has_job_description": bool((profile or {}).get("job_description")),
        "due_count": len(due_tasks),
    }


@router.post("/api/product-events", status_code=202)
async def record_product_event(
    payload: ProductEventRequest,
    request: Request,
) -> dict[str, bool]:
    """记录产品埋点事件（所有者范围，属性上限 8KB）。"""
    user_id = resolve_user_id(request, payload.user_id)
    if len(json.dumps(payload.properties, ensure_ascii=False, default=str)) > 8192:
        raise HTTPException(status_code=422, detail="事件属性不能超过 8KB")
    await run_sync(
        get_runtime().conversation_store.record_product_event,
        user_id=user_id,
        event_name=payload.event_name,
        session_id=payload.session_id,
        properties=payload.properties,
    )
    return {"accepted": True}
