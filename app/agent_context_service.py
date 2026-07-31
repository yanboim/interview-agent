"""Application-owned immutable context snapshot for one agent turn."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.capability import build_capability_profile
from app.chat_context import estimate_text_tokens


class ContextMemoryV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: str
    kind: Literal["fact", "preference", "goal", "observation"]
    content: str
    source_type: str
    source_id: str | None = None


class AgentContextSnapshotV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["agent-context-v1"] = "agent-context-v1"
    user_id: str
    role: str
    profile: dict[str, str | None]
    memories: tuple[ContextMemoryV1, ...] = ()
    weaknesses: tuple[str, ...] = ()
    due_learning_tasks: tuple[dict[str, str], ...] = ()
    conversation_summary: str = ""
    recent_messages: tuple[dict[str, str], ...] = ()
    estimated_tokens: int = 0

    def render_system_context(self) -> str:
        payload = self.model_dump(exclude={"recent_messages", "estimated_tokens"})
        return (
            "以下是服务端构建的只读用户上下文快照。只把 confirmed 记忆视为用户"
            "长期事实；不得从助手历史推断新的长期记忆。\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )


class AgentContextService:
    def __init__(self, repository: Any, *, token_budget: int = 4000) -> None:
        if token_budget < 500:
            raise ValueError("agent context reserve must be at least 500 tokens")
        self.repository = repository
        self.token_budget = token_budget

    @staticmethod
    def _clip(value: object, limit: int) -> str:
        text = str(value or "").strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def build(
        self,
        *,
        user_id: str,
        role: str,
        conversation_messages: list[dict[str, str]],
    ) -> AgentContextSnapshotV1:
        profile = self.repository.get_user_profile(user_id=user_id) or {}
        memories = self.repository.list_coaching_memories(
            user_id=user_id,
            status="confirmed",
            context_ready_only=True,
        )
        capability = build_capability_profile(
            self.repository.get_capability_rows(user_id=user_id)
        )
        tasks = self.repository.list_learning_tasks(user_id=user_id)
        summary = next(
            (
                item["content"]
                for item in conversation_messages
                if item.get("role") == "system"
            ),
            "",
        )
        recent = tuple(
            {"role": item["role"], "content": self._clip(item["content"], 1200)}
            for item in conversation_messages
            if item.get("role") in {"user", "assistant"}
        )[-8:]
        selected_memories = tuple(
            ContextMemoryV1(
                memory_id=str(item["memory_id"]),
                kind=str(item["kind"]),
                content=self._clip(item["content"], 500),
                source_type=str(item["source_type"]),
                source_id=str(item["source_id"]) if item.get("source_id") else None,
            )
            for item in memories[:10]
        )
        due_tasks = tuple(
            {
                "task_id": str(item["task_id"]),
                "dimension": self._clip(item["dimension"], 100),
                "action": self._clip(item["action"], 300),
                "due_at": str(item["due_at"]),
            }
            for item in tasks
            if item.get("status") != "completed"
        )[:5]
        base = {
            "schema_version": "agent-context-v1",
            "user_id": user_id,
            "role": role,
            "profile": {
                "target_role": self._clip(profile.get("target_role"), 100),
                "experience_level": self._clip(
                    profile.get("experience_level"), 30
                ),
                "focus_areas": self._clip(profile.get("focus_areas"), 300),
                "interview_date": (
                    str(profile.get("interview_date"))
                    if profile.get("interview_date")
                    else None
                ),
                "job_description": self._clip(
                    profile.get("job_description"), 1200
                ),
            },
            "memories": selected_memories,
            "weaknesses": tuple(
                self._clip(item.get("label"), 300)
                for item in capability.get("weaknesses", [])[:5]
            ),
            "due_learning_tasks": due_tasks,
            "conversation_summary": self._clip(summary, 1200),
            "recent_messages": recent,
        }
        snapshot = AgentContextSnapshotV1(**base)
        estimated = estimate_text_tokens(snapshot.render_system_context())
        if estimated > self.token_budget:
            base["profile"]["job_description"] = ""
            base["conversation_summary"] = ""
            snapshot = AgentContextSnapshotV1(**base)
            estimated = estimate_text_tokens(snapshot.render_system_context())
        while estimated > self.token_budget and base["due_learning_tasks"]:
            base["due_learning_tasks"] = base["due_learning_tasks"][:-1]
            snapshot = AgentContextSnapshotV1(**base)
            estimated = estimate_text_tokens(snapshot.render_system_context())
        while estimated > self.token_budget and base["memories"]:
            base["memories"] = base["memories"][:-1]
            snapshot = AgentContextSnapshotV1(**base)
            estimated = estimate_text_tokens(snapshot.render_system_context())
        if estimated > self.token_budget:
            raise ValueError("agent context snapshot exceeds reserved budget")
        return snapshot.model_copy(update={"estimated_tokens": estimated})
