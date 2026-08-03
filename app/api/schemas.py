"""HTTP 请求/响应 DTO 与边界校验，不包含业务状态转换。"""

import base64
import binascii
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """发起一次聊天请求的 DTO（含会话与消息内容）。"""

    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        """剥离空白；纯空白视为非法，统一为 422。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class ChatResponse(BaseModel):
    """聊天回合完成的响应 DTO。"""

    user_id: str
    session_id: str
    turn_id: str
    answer: str


class AssistantFeedbackRequest(BaseModel):
    """对某一助手回合点赞/点踩及原因的 DTO。"""

    user_id: str = Field(min_length=1, max_length=128)
    rating: Literal["up", "down"]
    reason_code: Literal[
        "incorrect", "unsupported", "irrelevant", "unclear", "other"
    ] | None = None
    comment: str | None = Field(default=None, max_length=2000)


class EvaluationCandidateReviewRequest(BaseModel):
    """管理员审核评测候选（批准/拒绝）的 DTO。"""

    decision: Literal["approved", "rejected"]
    approved_payload: dict[str, object] | None = None


class HistoryMessage(BaseModel):
    """历史消息条目的响应 DTO。"""

    role: str
    content: str
    created_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UserProfileRequest(BaseModel):
    """更新用户档案的 DTO（目标岗位、经验、方向、面试日期、JD）。"""

    user_id: str = Field(min_length=1, max_length=128)
    target_role: str = Field(min_length=1, max_length=100)
    experience_level: Literal["初级", "中级", "高级", "专家"]
    focus_areas: str = Field(default="", max_length=300)
    interview_date: str | None = Field(default=None, max_length=40)
    job_description: str = Field(default="", max_length=10000)

    @field_validator("user_id", "target_role", "focus_areas", "job_description")
    @classmethod
    def clean_profile_text(cls, value: str) -> str:
        """剥离文本字段首尾空白。"""
        return value.strip()

    @field_validator("interview_date")
    @classmethod
    def validate_interview_date(cls, value: str | None) -> str | None:
        """校验面试日期为合法 ISO 格式，空值跳过。"""
        if not value:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("interview_date 必须是 ISO 日期") from exc
        return value


class CoachingMemoryCreateRequest(BaseModel):
    """提议一条长期训练记忆的 DTO。"""

    user_id: str = Field(min_length=1, max_length=128)
    kind: Literal["fact", "preference", "goal", "observation"]
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("user_id", "content")
    @classmethod
    def clean_memory_text(cls, value: str) -> str:
        """剥离并拒绝纯空白文本。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class CoachingMemoryUpdateRequest(BaseModel):
    """确认/纠正/拒绝一条记忆的 DTO（纠正需带新内容）。"""

    user_id: str = Field(min_length=1, max_length=128)
    action: Literal["confirm", "reject", "correct"]
    content: str | None = Field(default=None, max_length=2000)

    @field_validator("content")
    @classmethod
    def clean_optional_memory_text(cls, value: str | None) -> str | None:
        """可选内容的空白剥离。"""
        return value.strip() if value is not None else None


class ProductEventRequest(BaseModel):
    """记录产品埋点事件的 DTO。"""

    user_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    event_name: str = Field(min_length=1, max_length=100)
    properties: dict[str, object] = Field(default_factory=dict)

    @field_validator("user_id", "event_name")
    @classmethod
    def clean_event_text(cls, value: str) -> str:
        """剥离并拒绝纯空白文本。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        """约束事件名为 ``snake/kebab.dot`` 形式，便于聚合统计。"""
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*", value):
            raise ValueError("event_name 仅支持小写字母、数字、点、短横线和下划线")
        return value


class ConversationSummary(BaseModel):
    """会话摘要条目的响应 DTO。"""

    session_id: str
    title: str
    mode: str
    archived_at: str | None = None
    created_at: str
    updated_at: str


class InterviewStartRequest(BaseModel):
    """开始一场模拟面试的 DTO（可选定向到简历评估）。"""

    user_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=200)
    level: str = Field(default="高级", min_length=1, max_length=30)
    question_count: int = Field(default=5, ge=1, le=20)
    resume_analysis_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    @field_validator("user_id", "topic", "level")
    @classmethod
    def clean_values(cls, value: str) -> str:
        """剥离并拒绝纯空白文本。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class InterviewAnswerRequest(BaseModel):
    """提交模拟面试答案的 DTO。"""

    user_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=20000)

    @field_validator("user_id", "answer")
    @classmethod
    def clean_values(cls, value: str) -> str:
        """剥离并拒绝纯空白文本。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class UserIdentityRequest(BaseModel):
    """仅含用户身份的复用基类 DTO（旧式 API 接受客户端 user_id）。"""

    user_id: str = Field(min_length=1, max_length=128)

    @field_validator("user_id")
    @classmethod
    def clean_user_id(cls, value: str) -> str:
        """剥离并拒绝纯空白 user_id。"""
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class ResumeAnalysisRequest(BaseModel):
    """为已存在简历创建评估的 DTO（提供 JD）。"""

    job_description: str = Field(default="", max_length=20_000)

    @field_validator("job_description")
    @classmethod
    def clean_job_description(cls, value: str) -> str:
        """剥离 JD 文本首尾空白。"""
        return value.strip()


class ResumeDraftUpdateRequest(BaseModel):
    """更新优化稿草稿的 DTO（含乐观并发版本）。"""

    expected_revision: int = Field(ge=1)
    draft: dict[str, object]


class InterviewReviewTextRequest(BaseModel):
    """创建文本逐字稿复盘的 DTO。"""

    transcript: str = Field(min_length=1, max_length=200_000)


class InterviewReviewTranscriptUpdateRequest(BaseModel):
    """更新逐字稿草稿的 DTO（含乐观并发版本）。"""

    expected_revision: int = Field(ge=1)
    segments: list[dict[str, object]] = Field(min_length=1, max_length=2000)


class InterviewReviewConfirmRequest(BaseModel):
    """确认逐字稿版本并触发复盘分析的 DTO。"""

    expected_revision: int = Field(ge=1)


class InterviewArchiveRequest(UserIdentityRequest):
    """归档/取消归档面试的 DTO。"""

    archived: bool = True


class LearningTaskGenerateRequest(UserIdentityRequest):
    """生成学习任务候选的 DTO（可选主题）。"""

    topic: str | None = Field(default=None, max_length=200)


class AgentRunCreateRequest(UserIdentityRequest):
    """提议训练方案工作流的 DTO（可选主题）。"""

    topic: str | None = Field(default=None, max_length=200)


class AgentRunRecoveryRequest(BaseModel):
    """回收僵死工作流步骤的 DTO（管理员用）。"""

    stale_seconds: int = Field(default=300, ge=30, le=86400)


class LearningTaskUpdateRequest(UserIdentityRequest):
    """更新学习任务状态或截止时间的 DTO。"""

    status: Literal["todo", "in_progress", "completed"] | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """要求截止时间带时区，避免跨时区歧义。"""
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at 必须包含时区")
        return value


class LearningTaskReviewRequest(UserIdentityRequest):
    """回顾一次间隔复习的 DTO（回忆结果与难度）。"""

    outcome: Literal["remembered", "partial", "forgotten"]
    difficulty: int = Field(ge=1, le=5)


class ConversationRenameRequest(UserIdentityRequest):
    """重命名会话标题的 DTO。"""

    title: str = Field(min_length=1, max_length=60)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        """剥离并拒绝空标题。"""
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ConversationArchiveRequest(UserIdentityRequest):
    """批量归档会话的 DTO（去重并校验 session_id）。"""

    session_ids: list[str] = Field(min_length=1, max_length=100)
    archived: bool = True

    @field_validator("session_ids")
    @classmethod
    def clean_session_ids(cls, values: list[str]) -> list[str]:
        """去空白、去重、按长度校验 session_id 列表。"""
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned or any(len(value) > 128 for value in cleaned):
            raise ValueError("session_ids 不合法")
        return list(dict.fromkeys(cleaned))


class AuthCredentials(BaseModel):
    """注册/登录凭据 DTO（用户名小写化、密码长度策略）。"""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """用户名小写化并约束字符集，保证大小写无关且无注入。"""
        value = value.strip().casefold()
        if not value or not all(
            character.isalnum() or character in "._-" for character in value
        ):
            raise ValueError("用户名只能包含字母、数字、点、下划线和短横线")
        return value


class RefreshTokenRequest(BaseModel):
    """刷新访问令牌的 DTO。"""

    refresh_token: str = Field(min_length=20, max_length=500)


class LogoutRequest(BaseModel):
    """登出请求的 DTO（可选附带的刷新令牌）。"""

    refresh_token: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    """已登录用户改密的 DTO（新密码需满足强度策略）。"""

    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("new_password")
    @classmethod
    def require_strong_password(cls, value: str) -> str:
        """强制新密码至少包含大小写字母/数字中的两类。"""
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ResetPasswordRequest(BaseModel):
    """用恢复码重置密码的 DTO（恢复码大写化、新密码强度策略）。"""

    username: str = Field(min_length=3, max_length=100)
    recovery_code: str = Field(min_length=20, max_length=40)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_reset_username(cls, value: str) -> str:
        """用户名小写化。"""
        return value.strip().casefold()

    @field_validator("recovery_code")
    @classmethod
    def normalize_recovery_code(cls, value: str) -> str:
        """恢复码统一大写化，避免大小写差异导致的比对失败。"""
        return value.strip().upper()

    @field_validator("new_password")
    @classmethod
    def require_strong_reset_password(cls, value: str) -> str:
        """强制新密码至少包含大小写字母/数字中的两类。"""
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ReminderPreferencesRequest(UserIdentityRequest):
    """更新提醒偏好的 DTO（HH:MM 时间与 IANA 时区）。"""

    enabled: bool
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)


class ProfileAvatarRequest(UserIdentityRequest):
    """更新头像的 DTO（data URL，校验格式、解码与大小、魔术字节）。"""

    avatar_data_url: str | None = Field(default=None, max_length=700_000)

    @field_validator("avatar_data_url")
    @classmethod
    def validate_avatar_data_url(cls, value: str | None) -> str | None:
        """校验头像为合法的 JPEG/PNG/WebP 且 ≤500KB。

        同时校验 base64 解码与文件魔术字节，防止仅靠扩展名伪装的恶意文件。
        """
        if value is None:
            return None
        match = re.fullmatch(
            r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})",
            value,
        )
        if not match:
            raise ValueError("头像仅支持 JPEG、PNG 或 WebP 图片")
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("头像图片编码无效") from exc
        if not raw or len(raw) > 512_000:
            raise ValueError("头像图片不能超过 500 KB")
        mime = match.group(1)
        signatures = {
            "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
            "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": raw.startswith(b"RIFF")
            and len(raw) >= 12
            and raw[8:12] == b"WEBP",
        }
        if not signatures[mime]:
            raise ValueError("头像图片内容与格式不匹配")
        return value


class AdminUserRoleRequest(BaseModel):
    """管理员修改用户角色的 DTO。"""

    role: Literal["user", "admin"]


class KnowledgeFileRequest(BaseModel):
    """管理员保存知识源文件的 DTO（文件名白名单防越权）。"""

    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1_000_000)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """只允许安全的 .md/.txt 文件名，拒绝路径穿越。"""
        filename = value.strip()
        if (
            Path(filename).name != filename
            or filename in {".", ".."}
            or Path(filename).suffix.lower() not in {".md", ".txt"}
        ):
            raise ValueError("仅支持安全的 .md 或 .txt 文件名")
        return filename


class KnowledgeRollbackRequest(BaseModel):
    """知识库回滚目标版本的 DTO（物理 collection 名）。"""

    collection_name: str = Field(min_length=1, max_length=255)
