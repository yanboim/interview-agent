import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    turn_id: str
    answer: str


class HistoryMessage(BaseModel):
    role: str
    content: str
    created_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UserProfileRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    target_role: str = Field(min_length=1, max_length=100)
    experience_level: Literal["初级", "中级", "高级", "专家"]
    focus_areas: str = Field(default="", max_length=300)
    interview_date: str | None = Field(default=None, max_length=40)
    job_description: str = Field(default="", max_length=10000)

    @field_validator("user_id", "target_role", "focus_areas", "job_description")
    @classmethod
    def clean_profile_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("interview_date")
    @classmethod
    def validate_interview_date(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("interview_date 必须是 ISO 日期") from exc
        return value


class ProductEventRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    event_name: str = Field(min_length=1, max_length=100)
    properties: dict[str, object] = Field(default_factory=dict)

    @field_validator("user_id", "event_name")
    @classmethod
    def clean_event_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*", value):
            raise ValueError("event_name 仅支持小写字母、数字、点、短横线和下划线")
        return value


class ConversationSummary(BaseModel):
    session_id: str
    title: str
    mode: str
    archived_at: str | None = None
    created_at: str
    updated_at: str


class InterviewStartRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=200)
    level: str = Field(default="高级", min_length=1, max_length=30)
    question_count: int = Field(default=5, ge=1, le=20)

    @field_validator("user_id", "topic", "level")
    @classmethod
    def clean_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class InterviewAnswerRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=20000)

    @field_validator("user_id", "answer")
    @classmethod
    def clean_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class UserIdentityRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)

    @field_validator("user_id")
    @classmethod
    def clean_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class InterviewArchiveRequest(UserIdentityRequest):
    archived: bool = True


class LearningTaskGenerateRequest(UserIdentityRequest):
    topic: str | None = Field(default=None, max_length=200)


class LearningTaskUpdateRequest(UserIdentityRequest):
    status: Literal["todo", "in_progress", "completed"] | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at 必须包含时区")
        return value


class ConversationRenameRequest(UserIdentityRequest):
    title: str = Field(min_length=1, max_length=60)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ConversationArchiveRequest(UserIdentityRequest):
    session_ids: list[str] = Field(min_length=1, max_length=100)
    archived: bool = True

    @field_validator("session_ids")
    @classmethod
    def clean_session_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned or any(len(value) > 128 for value in cleaned):
            raise ValueError("session_ids 不合法")
        return list(dict.fromkeys(cleaned))


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip().casefold()
        if not value or not all(
            character.isalnum() or character in "._-" for character in value
        ):
            raise ValueError("用户名只能包含字母、数字、点、下划线和短横线")
        return value


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("new_password")
    @classmethod
    def require_strong_password(cls, value: str) -> str:
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    recovery_code: str = Field(min_length=20, max_length=40)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_reset_username(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("recovery_code")
    @classmethod
    def normalize_recovery_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("new_password")
    @classmethod
    def require_strong_reset_password(cls, value: str) -> str:
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ReminderPreferencesRequest(UserIdentityRequest):
    enabled: bool
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)


class AdminUserRoleRequest(BaseModel):
    role: Literal["user", "admin"]


class KnowledgeFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1_000_000)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        filename = value.strip()
        if (
            Path(filename).name != filename
            or filename in {".", ".."}
            or Path(filename).suffix.lower() not in {".md", ".txt"}
        ):
            raise ValueError("仅支持安全的 .md 或 .txt 文件名")
        return filename


class KnowledgeRollbackRequest(BaseModel):
    collection_name: str = Field(min_length=1, max_length=255)
