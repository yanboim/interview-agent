"""Agent 工作流应用服务的生命周期与所有者封闭测试。"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.application.agent_run_service import AgentRunConflict, AgentRunService
from app.database import agent_runs, agent_steps
from app.storage import ConversationStore


def _row() -> dict[str, object]:
    return {
        "interview_id": "interview-1",
        "topic": "分布式系统",
        "level": "高级",
        "status": "completed",
        "source_type": "general",
        "turn_index": 1,
        "question": "如何设计限流？",
        "score": 5.0,
        "dimensions_json": json.dumps({
            "accuracy": 6,
            "depth": 4,
            "communication": 6,
            "practicality": 3,
        }),
        "weaknesses_json": json.dumps(["缺少故障降级方案"]),
        "updated_at": "2026-07-31T00:00:00+00:00",
    }


class RunRepository:
    def __init__(self, store: ConversationStore) -> None:
        self.store = store

    def get_capability_rows(self, *, user_id: str):
        return [_row()]

    def get_user_profile(self, *, user_id: str):
        return {"target_role": "Staff Backend Engineer"}

    def __getattr__(self, name: str):
        return getattr(self.store, name)


def test_training_run_is_idempotent_confirmed_once_and_replayed(tmp_path):
    store = ConversationStore(tmp_path / "agent-runs.db")
    service = AgentRunService(RunRepository(store))
    proposed = service.propose_training_program(
        user_id="user-a", topic="分布式系统", idempotency_key="program-1"
    )

    assert proposed["status"] == "awaiting_confirmation"
    assert proposed["proposal"]["target_role"] == "Staff Backend Engineer"
    assert store.list_learning_tasks(user_id="user-a") == []
    replay = service.propose_training_program(
        user_id="user-a", topic="分布式系统", idempotency_key="program-1"
    )
    assert replay["run_id"] == proposed["run_id"]
    with pytest.raises(ValueError, match="不同"):
        service.propose_training_program(
            user_id="user-a", topic="Java", idempotency_key="program-1"
        )

    completed = service.confirm(user_id="user-a", run_id=str(proposed["run_id"]))
    replayed = service.confirm(user_id="user-a", run_id=str(proposed["run_id"]))
    assert completed and completed["status"] == "completed"
    assert replayed and replayed["result"] == completed["result"]
    assert len(store.list_learning_tasks(user_id="user-a")) >= 1
    assert completed["result"]["interview_create_url"] == "/interviews"
    assert completed["events"][-1]["event"] == "done"


def test_training_run_owner_cancel_and_concurrent_confirmation(tmp_path):
    store = ConversationStore(tmp_path / "agent-runs-concurrency.db")
    service = AgentRunService(RunRepository(store))
    cancelled = service.propose_training_program(
        user_id="user-a", topic=None, idempotency_key="cancel-me"
    )
    assert service.inspect(user_id="user-b", run_id=str(cancelled["run_id"])) is None
    assert service.confirm(user_id="user-b", run_id=str(cancelled["run_id"])) is None
    stopped = service.cancel(user_id="user-a", run_id=str(cancelled["run_id"]))
    assert stopped and stopped["status"] == "cancelled"

    run = service.propose_training_program(
        user_id="user-a", topic=None, idempotency_key="concurrent"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service.confirm, user_id="user-a", run_id=str(run["run_id"]))
            for _ in range(2)
        ]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except AgentRunConflict:
            outcomes.append(None)
    assert sum(item is not None and item["status"] == "completed" for item in outcomes) >= 1
    assert service.inspect(user_id="user-a", run_id=str(run["run_id"]))["status"] == "completed"


def test_stale_claim_is_recovered_and_retry_completes(tmp_path):
    store = ConversationStore(tmp_path / "agent-runs-recovery.db")
    service = AgentRunService(RunRepository(store))
    run = service.propose_training_program(
        user_id="user-a", topic=None, idempotency_key="recover-me"
    )
    run_id = str(run["run_id"])
    assert store.claim_agent_run_command(
        user_id="user-a", run_id=run_id, claim_owner="dead-worker"
    )["state"] == "claimed"
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with store.engine.begin() as connection:
        connection.execute(update(agent_steps).where(
            agent_steps.c.run_id == run_id,
            agent_steps.c.step_key == "create_tasks",
        ).values(claimed_at=stale))

    assert service.recover_stale(stale_seconds=30) == 1
    failed = service.inspect(user_id="user-a", run_id=run_id)
    assert failed and failed["status"] == "failed"
    completed = service.retry(user_id="user-a", run_id=run_id)
    assert completed and completed["status"] == "completed"


def test_partial_command_failure_is_durable_and_retryable(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "agent-runs-failure.db")
    service = AgentRunService(RunRepository(store))
    run = service.propose_training_program(
        user_id="user-a", topic=None, idempotency_key="fail-once"
    )
    original = store.complete_training_program_command

    def fail(**_kwargs):
        raise RuntimeError("simulated command failure")

    monkeypatch.setattr(store, "complete_training_program_command", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        service.confirm(user_id="user-a", run_id=str(run["run_id"]))
    failed = service.inspect(user_id="user-a", run_id=str(run["run_id"]))
    assert failed and failed["status"] == "failed"
    assert failed["error_code"] == "command_failed"
    assert store.list_learning_tasks(user_id="user-a") == []

    monkeypatch.setattr(store, "complete_training_program_command", original)
    completed = service.retry(user_id="user-a", run_id=str(run["run_id"]))
    assert completed and completed["status"] == "completed"


def test_admin_inspection_omits_user_owned_payloads(tmp_path):
    store = ConversationStore(tmp_path / "agent-runs-admin.db")
    service = AgentRunService(RunRepository(store))
    run = service.propose_training_program(
        user_id="user-a", topic="分布式系统", idempotency_key="admin-view"
    )

    inspected = service.inspect_for_admin(run_id=str(run["run_id"]))

    assert inspected
    assert "input" not in inspected
    assert "proposal" not in inspected
    assert "result" not in inspected
    assert all("result" not in step for step in inspected["steps"])
