"""SQLAlchemy Core 持久化适配器的测试。"""

import json

from app.storage import ConversationStore


def test_messages_persist_across_store_instances(tmp_path):
    database = tmp_path / "conversations.db"
    first = ConversationStore(database)
    first.append_message(
        user_id="user-1",
        session_id="session-1",
        role="user",
        content="解释 RAG",
    )

    second = ConversationStore(database)
    messages = second.get_messages(
        user_id="user-1",
        session_id="session-1",
    )

    assert [(message.role, message.content) for message in messages] == [
        ("user", "解释 RAG")
    ]


def test_message_source_metadata_persists(tmp_path):
    store = ConversationStore(tmp_path / "sources.db")
    metadata = {
        "knowledge_used": True,
        "schema_version": 1,
        "sources": [
            {"evidence_id": "chunk-1", "label": "jvm.md", "kind": "private"}
        ],
        "citations": [
            {
                "claim": "JDK 21 是 LTS。",
                "evidence_ids": ["chunk-1"],
                "support": "supported",
            }
        ],
        "unsupported_claims": [],
    }
    store.append_message(
        user_id="user-a",
        session_id="session-a",
        role="assistant",
        content="回答",
        metadata_json=json.dumps(metadata),
    )

    message = store.get_messages(
        user_id="user-a",
        session_id="session-a",
    )[0]
    assert message.metadata == metadata


def test_conversations_are_isolated_by_user(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.append_message(
        user_id="user-a",
        session_id="same-session",
        role="user",
        content="用户 A",
    )
    store.append_message(
        user_id="user-b",
        session_id="same-session",
        role="user",
        content="用户 B",
    )

    user_a = store.get_messages(
        user_id="user-a",
        session_id="same-session",
    )
    user_b = store.get_messages(
        user_id="user-b",
        session_id="same-session",
    )

    assert [message.content for message in user_a] == ["用户 A"]
    assert [message.content for message in user_b] == ["用户 B"]


def test_delete_conversation_only_deletes_owners_data(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    for user_id in ("user-a", "user-b"):
        store.append_message(
            user_id=user_id,
            session_id="same-session",
            role="user",
            content=user_id,
        )

    assert store.delete_conversation(
        user_id="user-a",
        session_id="same-session",
    )
    assert not store.get_messages(
        user_id="user-a",
        session_id="same-session",
    )
    assert store.get_messages(
        user_id="user-b",
        session_id="same-session",
    )


def test_rename_conversation_only_updates_owners_title(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    for user_id in ("user-a", "user-b"):
        store.append_message(
            user_id=user_id,
            session_id="same-session",
            role="user",
            content=f"{user_id} 的问题",
        )

    renamed = store.rename_conversation(
        user_id="user-a",
        session_id="same-session",
        title="RAG 面试准备",
    )

    assert renamed is not None
    assert renamed["title"] == "RAG 面试准备"
    assert store.list_conversations("user-b")[0]["title"] == "user-b 的问题"


def test_interview_turns_and_scores_persist(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.create_interview(
        user_id="user-a",
        interview_id="interview-1",
        topic="RAG",
        level="高级",
        total_questions=2,
        first_question="RAG 如何评估？",
    )

    status = store.save_interview_answer(
        user_id="user-a",
        interview_id="interview-1",
        turn_index=1,
        answer="使用 Recall@K 和 MRR。",
        score=8.0,
        feedback="需要补充生成侧评估。",
        dimensions_json='{"accuracy": 8}',
        strengths_json='["指标正确"]',
        weaknesses_json='["缺少忠实度"]',
        reference_answer="先定义检索和生成侧指标。",
        next_question="如何评估忠实度？",
    )

    turns = store.get_interview_turns(
        user_id="user-a",
        interview_id="interview-1",
    )
    assert status == "active"
    assert len(turns) == 2
    assert turns[0]["score"] == 8.0
    assert turns[0]["reference_answer"] == "先定义检索和生成侧指标。"
    assert turns[1]["question"] == "如何评估忠实度？"
    attempts = store.get_interview_answer_attempts(
        user_id="user-a",
        interview_id="interview-1",
        turn_index=1,
    )
    assert len(attempts) == 1
    assert attempts[0]["attempt_index"] == 1


def test_interview_answer_retry_keeps_attempt_history(tmp_path):
    store = ConversationStore(tmp_path / "retry.db")
    store.create_interview(
        user_id="user-a",
        interview_id="interview-1",
        topic="RAG",
        level="高级",
        total_questions=1,
        first_question="如何评估？",
    )
    store.save_interview_answer(
        user_id="user-a",
        interview_id="interview-1",
        turn_index=1,
        answer="使用 Recall@K。",
        score=6,
        feedback="缺少生成侧。",
        dimensions_json="{}",
        strengths_json="[]",
        weaknesses_json="[]",
        reference_answer="同时评估检索与生成。",
    )

    comparison = store.retry_interview_answer(
        user_id="user-a",
        interview_id="interview-1",
        turn_index=1,
        answer="检索用 Recall@K，生成用忠实度。",
        score=8.5,
        feedback="更完整。",
        dimensions_json="{}",
        strengths_json="[]",
        weaknesses_json="[]",
        reference_answer="同时评估检索与生成。",
    )

    attempts = store.get_interview_answer_attempts(
        user_id="user-a",
        interview_id="interview-1",
        turn_index=1,
    )
    assert [item["attempt_index"] for item in attempts] == [1, 2]
    assert comparison["previous_score"] == 6
    assert comparison["score_delta"] == 2.5
    assert store.get_interview(
        user_id="user-a",
        interview_id="interview-1",
    )["status"] == "completed"


def test_profiles_and_product_events_are_user_scoped(tmp_path):
    store = ConversationStore(tmp_path / "profiles.db")
    for user_id, role in (("user-a", "Java 工程师"), ("user-b", "产品经理")):
        store.upsert_user_profile(
            user_id=user_id,
            target_role=role,
            experience_level="高级",
            focus_areas="系统设计",
            interview_date=None,
            job_description="职位描述",
        )
        store.record_product_event(
            user_id=user_id,
            event_name="profile.goal_saved",
            session_id=None,
            properties={"role": role},
        )

    assert store.get_user_profile(user_id="user-a")["target_role"] == "Java 工程师"
    avatar = "data:image/png;base64,iVBORw0KGgo="
    updated = store.update_profile_avatar(
        user_id="user-a",
        avatar_data_url=avatar,
    )
    assert updated["avatar_data_url"] == avatar
    assert store.get_user_profile(user_id="user-b")["avatar_data_url"] is None
    events = store.list_product_events(user_id="user-a")
    assert len(events) == 1
    assert events[0]["user_id"] == "user-a"


def test_capability_rows_only_include_scored_turns_for_owner(tmp_path):
    store = ConversationStore(tmp_path / "capability.db")
    for user_id, score in (("user-a", 8.0), ("user-b", 4.0)):
        store.create_interview(
            user_id=user_id,
            interview_id="same-interview",
            topic="RAG",
            level="高级",
            total_questions=2,
            first_question="如何评估 RAG？",
        )
        store.save_interview_answer(
            user_id=user_id,
            interview_id="same-interview",
            turn_index=1,
            answer="Recall@K",
            score=score,
            feedback="继续完善",
            dimensions_json=f'{{"accuracy": {score}}}',
            strengths_json="[]",
            weaknesses_json='["缺少生成侧评估"]',
            next_question="如何评估忠实度？",
        )

    rows = store.get_capability_rows(user_id="user-a")

    assert len(rows) == 1
    assert rows[0]["score"] == 8.0
    assert rows[0]["question"] == "如何评估 RAG？"


def test_interview_history_can_archive_restore_and_delete(tmp_path):
    store = ConversationStore(tmp_path / "history.db")
    store.create_interview(
        user_id="user-a",
        interview_id="interview-1",
        topic="Java",
        level="高级",
        total_questions=2,
        first_question="解释 G1",
    )

    history = store.list_interviews(user_id="user-a")
    assert len(history) == 1
    assert history[0]["answered_questions"] == 0
    assert history[0]["average_score"] is None

    assert store.archive_interview(
        user_id="user-a",
        interview_id="interview-1",
    )
    assert store.list_interviews(user_id="user-a") == []
    assert store.list_interviews(
        user_id="user-a",
        include_archived=True,
    )[0]["archived_at"]

    assert store.archive_interview(
        user_id="user-a",
        interview_id="interview-1",
        archived=False,
    )
    assert store.list_interviews(user_id="user-a")[0]["archived_at"] is None
    assert store.delete_interview(
        user_id="user-a",
        interview_id="interview-1",
    )
    assert store.get_interview(
        user_id="user-a",
        interview_id="interview-1",
    ) is None


def test_learning_tasks_are_deduplicated_reviewed_and_isolated(tmp_path):
    store = ConversationStore(tmp_path / "learning.db")
    candidates = [
        {
            "dimension": "工程实践",
            "weakness": "缺少项目案例",
            "action": "补充一个真实案例。",
        },
        {
            "dimension": "原理深度",
            "weakness": "缺少底层原理",
            "action": "画图并复述。",
        },
    ]

    tasks = store.create_learning_tasks(
        user_id="user-a",
        candidates=candidates,
    )
    duplicated = store.create_learning_tasks(
        user_id="user-a",
        candidates=candidates,
    )

    assert len(tasks) == 2
    assert len(duplicated) == 2
    assert store.list_learning_tasks(user_id="user-b") == []

    task_id = str(tasks[0]["task_id"])
    updated = store.update_learning_task(
        user_id="user-a",
        task_id=task_id,
        status="in_progress",
    )
    assert updated["status"] == "in_progress"

    reviewed = store.review_learning_task(
        user_id="user-a",
        task_id=task_id,
        outcome="forgotten",
        difficulty=5,
    )
    assert reviewed["review_count"] == 1
    assert reviewed["last_reviewed_at"]
    assert reviewed["next_review_at"]
    assert reviewed["recall_outcome"] == "forgotten"
    assert reviewed["difficulty_rating"] == 5
    assert reviewed["lapse_count"] == 1
    assert float(reviewed["review_confidence"]) < 0.5

    assert store.delete_learning_task(
        user_id="user-a",
        task_id=task_id,
    )
    assert len(store.list_learning_tasks(user_id="user-a")) == 1


def test_conversation_archive_and_reminders(tmp_path):
    store = ConversationStore(tmp_path / "preferences.db")
    store.append_message(
        user_id="user-a",
        session_id="session-a",
        role="user",
        content="归档我",
    )
    assert store.archive_conversations(
        user_id="user-a",
        session_ids=["session-a"],
        archived=True,
    ) == 1
    assert store.list_conversations("user-a") == []
    archived = store.list_conversations("user-a", include_archived=True)
    assert archived[0]["archived_at"] is not None

    preferences = store.update_reminder_preferences(
        user_id="user-a",
        enabled=True,
        reminder_time="08:30",
        timezone="Asia/Shanghai",
    )
    assert preferences["reminder_enabled"] is True
    assert preferences["reminder_time"] == "08:30"
