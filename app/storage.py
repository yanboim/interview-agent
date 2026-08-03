"""SQLAlchemy Core 持久化适配器；每个写方法拥有完整业务事务和并发条件。"""

import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    create_engine,
    event,
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine

from app.repositories.chat_messages import (
    ChatMessageRepositoryMixin,
    StoredMessage,
)
from app.repositories.administration import AdministrationRepositoryMixin
from app.repositories.chat_turns import ChatTurnRepositoryMixin
from app.repositories.interviews import InterviewRepositoryMixin
from app.repositories.interview_reviews import InterviewReviewRepositoryMixin
from app.repositories.learning import LearningRepositoryMixin
from app.repositories.profiles import ProfileRepositoryMixin
from app.repositories.resumes import ResumeRepositoryMixin
from app.database import (
    agent_runs,
    agent_steps,
    assistant_feedback,
    audit_events,
    auth_tokens,
    chat_turns,
    conversations,
    deployment_releases,
    execution_traces,
    evaluation_candidates,
    interview_answer_attempts,
    interview_review_turns,
    interview_reviews,
    interview_turns,
    interviews,
    learning_tasks,
    messages,
    metadata,
    normalize_database_url,
    product_events,
    resume_analyses,
    resume_documents,
    tool_audit_logs,
    user_profiles,
    users,
)


class ConversationStore(
    AdministrationRepositoryMixin,
    ChatMessageRepositoryMixin,
    ChatTurnRepositoryMixin,
    InterviewRepositoryMixin,
    InterviewReviewRepositoryMixin,
    LearningRepositoryMixin,
    ProfileRepositoryMixin,
    ResumeRepositoryMixin,
):
    """SQLAlchemy Core 持久化适配器：用户、会话、面试、简历、复盘与审计的事务脚本。

    遵循架构契约：每个写方法拥有一个完整的 ``engine.begin()`` 业务事务，
    每个读方法拥有一个 ``engine.connect()`` 边界；外部模型与网络调用绝不
    进入这些事务。业务并发安全完全依赖条件更新、唯一约束、外键、幂等键与
    所有者令牌（claim_token/claim_owner）；唯一的进程内锁仅用于可选的
    ``create_all`` 初始化，不参与业务正确性。所有用户拥有的查询/变更都
    必须带 ``user_id``（服务端解析），客户端 ID 不是授权依据。
    """

    def __init__(
        self,
        database: str | Path,
        *,
        auto_create_schema: bool = True,
    ) -> None:
        """注入数据库地址并构建引擎；本地/测试可自动建表，生产走 Alembic。"""
        self.database_url = normalize_database_url(database)
        self.auto_create_schema = auto_create_schema
        if self.database_url.startswith("sqlite:///"):
            sqlite_path = Path(self.database_url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args=(
                {"check_same_thread": False}
                if self.database_url.startswith("sqlite:")
                else {}
            ),
        )
        if self.database_url.startswith("sqlite:"):
            @event.listens_for(self.engine, "connect")
            def enable_sqlite_foreign_keys(
                dbapi_connection,
                _connection_record,
            ) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()
        # 此锁只避免单进程重复执行 create_all；业务并发完全依赖事务、条件更新和约束。
        self._initialization_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._initialization_lock:
            if self._initialized:
                return
            if self.auto_create_schema:
                metadata.create_all(self.engine)
            self._initialized = True

    def check_connection(self) -> None:
        self.initialize()
        with self.engine.connect() as connection:
            connection.execute(select(1))
            connection.execute(select(conversations.c.user_id).limit(1))

    def system_counts(self) -> dict[str, int]:
        self.initialize()
        tables = {
            "users": users,
            "conversations": conversations,
            "messages": messages,
            "chat_turns": chat_turns,
            "interviews": interviews,
            "interview_turns": interview_turns,
            "learning_tasks": learning_tasks,
            "agent_runs": agent_runs,
            "agent_steps": agent_steps,
            "assistant_feedback": assistant_feedback,
            "evaluation_candidates": evaluation_candidates,
            "tool_audit_logs": tool_audit_logs,
            "audit_events": audit_events,
            "execution_traces": execution_traces,
            "user_profiles": user_profiles,
            "interview_answer_attempts": interview_answer_attempts,
            "product_events": product_events,
            "deployment_releases": deployment_releases,
            "resume_documents": resume_documents,
            "resume_analyses": resume_analyses,
            "interview_reviews": interview_reviews,
            "interview_review_turns": interview_review_turns,
        }
        now = datetime.now(UTC).isoformat()
        with self.engine.connect() as connection:
            counts = {
                name: int(
                    connection.execute(
                        select(func.count()).select_from(table)
                    ).scalar_one()
                )
                for name, table in tables.items()
            }
            counts["active_tokens"] = int(
                connection.execute(
                    select(func.count())
                    .select_from(auth_tokens)
                    .where(
                        auth_tokens.c.revoked_at.is_(None),
                        auth_tokens.c.expires_at > now,
                    )
                ).scalar_one()
            )
            return counts

    def list_users(self, *, limit: int = 200) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(
                users.c.user_id,
                users.c.username,
                users.c.role,
                users.c.created_at,
                users.c.updated_at,
                func.count(func.distinct(conversations.c.session_id)).label(
                    "conversation_count"
                ),
                func.count(func.distinct(interviews.c.interview_id)).label(
                    "interview_count"
                ),
            )
            .select_from(
                users.outerjoin(
                    conversations,
                    conversations.c.user_id == users.c.user_id,
                ).outerjoin(
                    interviews,
                    interviews.c.user_id == users.c.user_id,
                )
            )
            .group_by(
                users.c.user_id,
                users.c.username,
                users.c.role,
                users.c.created_at,
                users.c.updated_at,
            )
            .order_by(users.c.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def update_user_role(self, *, user_id: str, role: str) -> dict[str, object]:
        if role not in {"user", "admin"}:
            raise ValueError("不支持的用户角色")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            current = connection.execute(
                select(users.c.role).where(users.c.user_id == user_id)
            ).scalar_one_or_none()
            if current is None:
                raise ValueError("用户不存在")
            if current == "admin" and role != "admin":
                admin_count = connection.execute(
                    select(func.count())
                    .select_from(users)
                    .where(users.c.role == "admin")
                ).scalar_one()
                if int(admin_count) <= 1:
                    raise ValueError("不能降级系统中最后一个管理员")
            connection.execute(
                update(users)
                .where(users.c.user_id == user_id)
                .values(role=role, updated_at=now)
            )
            row = connection.execute(
                select(
                    users.c.user_id,
                    users.c.username,
                    users.c.role,
                    users.c.created_at,
                    users.c.updated_at,
                ).where(users.c.user_id == user_id)
            ).mappings().one()
        return dict(row)
