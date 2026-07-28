from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)


metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("username", String(100), nullable=False, unique=True),
    Column("password_hash", String(128), nullable=False),
    Column("password_salt", String(64), nullable=False),
    Column("recovery_code_hash", String(64)),
    Column("role", String(20), nullable=False, server_default="user"),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
)

auth_tokens = Table(
    "auth_tokens",
    metadata,
    Column("token_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("token_type", String(20), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("revoked_at", String(40)),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "token_type IN ('access', 'refresh')",
        name="ck_auth_tokens_type",
    ),
    ForeignKeyConstraint(
        ["user_id"],
        ["users.user_id"],
        ondelete="CASCADE",
    ),
)
Index("idx_auth_tokens_user", auth_tokens.c.user_id, auth_tokens.c.token_type)

conversations = Table(
    "conversations",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("session_id", String(128), primary_key=True),
    Column("title", String(200), nullable=False, server_default="新会话"),
    Column("mode", String(30), nullable=False, server_default="chat"),
    Column("archived_at", String(40)),
    Column(
        "next_chat_turn_index",
        Integer,
        nullable=False,
        server_default="1",
    ),
    Column("active_chat_turn_id", String(128)),
    Column("chat_summary", Text, nullable=False, server_default=""),
    Column("chat_summary_through_message_id", Integer),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)
Index(
    "idx_conversations_user_archived_updated",
    conversations.c.user_id,
    conversations.c.archived_at,
    conversations.c.updated_at,
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False),
    Column("session_id", String(128), nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("metadata_json", Text),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    ForeignKeyConstraint(
        ["user_id", "session_id"],
        ["conversations.user_id", "conversations.session_id"],
        ondelete="CASCADE",
    ),
)
Index(
    "idx_messages_conversation",
    messages.c.user_id,
    messages.c.session_id,
    messages.c.id,
)

interviews = Table(
    "interviews",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("interview_id", String(128), primary_key=True),
    Column("topic", String(200), nullable=False),
    Column("level", String(30), nullable=False),
    Column("total_questions", Integer, nullable=False),
    Column("status", String(30), nullable=False, server_default="active"),
    Column("archived_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

user_profiles = Table(
    "user_profiles",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("target_role", String(100), nullable=False),
    Column("experience_level", String(30), nullable=False),
    Column("focus_areas", String(300), nullable=False, server_default=""),
    Column("interview_date", String(40)),
    Column("job_description", Text, nullable=False, server_default=""),
    Column("reminder_enabled", Boolean, nullable=False, server_default="0"),
    Column("reminder_time", String(5), nullable=False, server_default="09:00"),
    Column("reminder_timezone", String(64), nullable=False, server_default="UTC"),
    Column("avatar_data_url", Text),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

chat_turns = Table(
    "chat_turns",
    metadata,
    Column("turn_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("session_id", String(128), nullable=False),
    Column("turn_index", Integer, nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("request_content", Text, nullable=False),
    Column("status", String(20), nullable=False, server_default="pending"),
    Column("claim_token", String(128)),
    Column("assistant_content", Text),
    Column("metadata_json", Text),
    Column("error", Text),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'generating', 'completed', 'failed', 'cancelled')",
        name="ck_chat_turn_status",
    ),
    UniqueConstraint(
        "user_id",
        "session_id",
        "turn_index",
        name="uq_chat_turn_index",
    ),
    UniqueConstraint(
        "user_id",
        "session_id",
        "idempotency_key",
        name="uq_chat_turn_idempotency",
    ),
    ForeignKeyConstraint(
        ["user_id", "session_id"],
        ["conversations.user_id", "conversations.session_id"],
        ondelete="CASCADE",
    ),
)
Index(
    "idx_chat_turns_session_status",
    chat_turns.c.user_id,
    chat_turns.c.session_id,
    chat_turns.c.status,
)

interview_turns = Table(
    "interview_turns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False),
    Column("interview_id", String(128), nullable=False),
    Column("turn_index", Integer, nullable=False),
    Column("question", Text, nullable=False),
    Column("answer", Text),
    Column("score", Float),
    Column("feedback", Text),
    Column("dimensions_json", Text),
    Column("strengths_json", Text),
    Column("weaknesses_json", Text),
    Column("reference_answer", Text),
    Column(
        "submission_status",
        String(20),
        nullable=False,
        server_default="pending",
    ),
    Column("idempotency_key", String(128)),
    Column("answer_digest", String(64)),
    Column("claim_token", String(128)),
    Column("result_json", Text),
    Column("submission_error", Text),
    Column("processing_started_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint(
        "submission_status IN ('pending', 'generating', 'completed', 'failed')",
        name="ck_interview_turn_submission_status",
    ),
    UniqueConstraint(
        "user_id",
        "interview_id",
        "turn_index",
        name="uq_interview_turn",
    ),
    UniqueConstraint(
        "user_id",
        "interview_id",
        "idempotency_key",
        name="uq_interview_turn_idempotency",
    ),
    ForeignKeyConstraint(
        ["user_id", "interview_id"],
        ["interviews.user_id", "interviews.interview_id"],
        ondelete="CASCADE",
    ),
)

interview_answer_attempts = Table(
    "interview_answer_attempts",
    metadata,
    Column("attempt_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("interview_id", String(128), nullable=False),
    Column("turn_index", Integer, nullable=False),
    Column("attempt_index", Integer, nullable=False),
    Column("answer", Text, nullable=False),
    Column("score", Float, nullable=False),
    Column("feedback", Text, nullable=False),
    Column("dimensions_json", Text, nullable=False),
    Column("strengths_json", Text, nullable=False),
    Column("weaknesses_json", Text, nullable=False),
    Column("reference_answer", Text),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint(
        "user_id",
        "interview_id",
        "turn_index",
        "attempt_index",
        name="uq_interview_answer_attempt",
    ),
    ForeignKeyConstraint(
        ["user_id", "interview_id"],
        ["interviews.user_id", "interviews.interview_id"],
        ondelete="CASCADE",
    ),
)
Index(
    "idx_interview_attempts_turn",
    interview_answer_attempts.c.user_id,
    interview_answer_attempts.c.interview_id,
    interview_answer_attempts.c.turn_index,
)

learning_tasks = Table(
    "learning_tasks",
    metadata,
    Column("task_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("source_interview_id", String(128)),
    Column("dimension", String(100), nullable=False),
    Column("weakness", String(300), nullable=False),
    Column("action", Text, nullable=False),
    Column("status", String(30), nullable=False, server_default="todo"),
    Column("due_at", String(40), nullable=False),
    Column("review_count", Integer, nullable=False, server_default="0"),
    Column("last_reviewed_at", String(40)),
    Column("next_review_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint(
        "status IN ('todo', 'in_progress', 'completed')",
        name="ck_learning_tasks_status",
    ),
)
Index(
    "idx_learning_tasks_user_status",
    learning_tasks.c.user_id,
    learning_tasks.c.status,
    learning_tasks.c.due_at,
)

tool_audit_logs = Table(
    "tool_audit_logs",
    metadata,
    Column("audit_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("role", String(20), nullable=False),
    Column("tool_name", String(100), nullable=False),
    Column("input_summary", String(500), nullable=False),
    Column("status", String(30), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("result_summary", String(500)),
    Column("request_id", String(128)),
    Column("interaction_type", String(30)),
    Column("interaction_id", String(256)),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "status IN ('success', 'error', 'denied')",
        name="ck_tool_audit_status",
    ),
)
Index(
    "idx_tool_audit_user_created",
    tool_audit_logs.c.user_id,
    tool_audit_logs.c.created_at,
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("event_id", String(128), primary_key=True),
    Column("request_id", String(128), nullable=False),
    Column("actor_user_id", String(128)),
    Column("actor_username", String(100)),
    Column("actor_role", String(20)),
    Column("action", String(160), nullable=False),
    Column("resource_type", String(80), nullable=False),
    Column("resource_id", String(256)),
    Column("outcome", String(20), nullable=False),
    Column("method", String(10), nullable=False),
    Column("path", String(300), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("detail_json", Text, nullable=False, server_default="{}"),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "outcome IN ('success', 'error', 'denied')",
        name="ck_audit_events_outcome",
    ),
)
Index(
    "idx_audit_events_created",
    audit_events.c.created_at,
)
Index(
    "idx_audit_events_actor_created",
    audit_events.c.actor_user_id,
    audit_events.c.created_at,
)
Index(
    "idx_audit_events_action_created",
    audit_events.c.action,
    audit_events.c.created_at,
)

execution_traces = Table(
    "execution_traces",
    metadata,
    Column("trace_id", String(128), primary_key=True),
    Column("request_id", String(128), nullable=False),
    Column("user_id", String(128), nullable=False),
    Column("interaction_type", String(30), nullable=False),
    Column("interaction_id", String(256), nullable=False),
    Column("stage", String(80), nullable=False),
    Column("status", String(30), nullable=False),
    Column("duration_ms", Integer),
    Column("detail_json", Text, nullable=False, server_default="{}"),
    Column("created_at", String(40), nullable=False),
)
Index(
    "idx_execution_trace_interaction",
    execution_traces.c.interaction_type,
    execution_traces.c.interaction_id,
    execution_traces.c.created_at,
)
Index(
    "idx_execution_trace_request",
    execution_traces.c.request_id,
    execution_traces.c.created_at,
)

product_events = Table(
    "product_events",
    metadata,
    Column("event_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False),
    Column("session_id", String(128)),
    Column("event_name", String(100), nullable=False),
    Column("properties_json", Text, nullable=False, server_default="{}"),
    Column("created_at", String(40), nullable=False),
)
Index(
    "idx_product_events_user_created",
    product_events.c.user_id,
    product_events.c.created_at,
)

deployment_releases = Table(
    "deployment_releases",
    metadata,
    Column("release_id", String(128), primary_key=True),
    Column("version", String(100), nullable=False),
    Column("title", String(200), nullable=False),
    Column("summary", Text, nullable=False, server_default=""),
    Column("environment", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("commit_sha", String(64)),
    Column("changes_json", Text, nullable=False, server_default="[]"),
    Column("verification_json", Text, nullable=False, server_default="{}"),
    Column("app_image", String(200)),
    Column("worker_image", String(200)),
    Column("migration_revision", String(64)),
    Column("recovery_point", String(200)),
    Column("triggered_by", String(100), nullable=False),
    Column("started_at", String(40), nullable=False),
    Column("completed_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint(
        "environment IN ('canary', 'production')",
        name="ck_deployment_releases_environment",
    ),
    CheckConstraint(
        "status IN ('deploying', 'succeeded', 'failed', 'rolled_back')",
        name="ck_deployment_releases_status",
    ),
)
Index(
    "idx_deployment_releases_environment_completed",
    deployment_releases.c.environment,
    deployment_releases.c.completed_at,
)


def normalize_database_url(value: str | Path) -> str:
    if isinstance(value, Path):
        return f"sqlite:///{value}"
    if "://" in value:
        return value
    return f"sqlite:///{value}"
