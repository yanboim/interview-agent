from app.application.chat_service import ChatTurnService
from app.storage import ConversationStore


def _completed_turn(store: ConversationStore, *, user_id: str = "user-a") -> str:
    service = ChatTurnService(store)
    claim = service.begin(
        user_id=user_id,
        session_id="session-a",
        content="如何验证 Agent？",
        idempotency_key=f"feedback-{user_id}",
    )
    service.complete(
        claim,
        user_id=user_id,
        session_id="session-a",
        answer="使用冻结数据集和分组门禁。",
        metadata={
            "turn_id": claim["turn_id"],
            "prompt_version": "chat-v2",
            "schema_version": "specialist-result-v1",
            "model_version": "mock-v1",
            "sources": [{"evidence_id": "source-2"}, {"evidence_id": "source-1"}],
        },
    )
    return str(claim["turn_id"])


def test_feedback_is_owner_scoped_versioned_and_privacy_reviewed(tmp_path):
    store = ConversationStore(tmp_path / "feedback.db")
    turn_id = _completed_turn(store)

    assert store.upsert_assistant_feedback(
        user_id="user-b", turn_id=turn_id, rating="down"
    ) is None
    feedback = store.upsert_assistant_feedback(
        user_id="user-a",
        turn_id=turn_id,
        rating="down",
        reason_code="missing_evidence",
        comment="包含用户私有内容，不应直接进入评测集",
    )

    assert feedback is not None
    assert feedback["prompt_version"] == "chat-v2"
    assert feedback["source_ids"] == ["source-1", "source-2"]
    pending = store.list_evaluation_candidates()
    assert len(pending) == 1
    assert "comment" not in pending[0]
    assert "approved_payload_json" not in pending[0]

    reviewed = store.review_evaluation_candidate(
        candidate_id=str(pending[0]["candidate_id"]),
        reviewer_id="admin-1",
        decision="approved",
        approved_payload={"input": "已脱敏问题", "expected": "已审阅答案"},
    )
    assert reviewed is not None
    assert reviewed["status"] == "approved"
    assert not store.delete_assistant_feedback(user_id="user-a", turn_id=turn_id)


def test_positive_feedback_never_enters_candidate_queue(tmp_path):
    store = ConversationStore(tmp_path / "positive-feedback.db")
    turn_id = _completed_turn(store)
    store.upsert_assistant_feedback(user_id="user-a", turn_id=turn_id, rating="down")
    assert len(store.list_evaluation_candidates()) == 1

    store.upsert_assistant_feedback(user_id="user-a", turn_id=turn_id, rating="up")

    assert store.list_evaluation_candidates() == []
