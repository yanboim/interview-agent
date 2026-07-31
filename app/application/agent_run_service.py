"""Application-owned durable Agent workflow lifecycle."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.capability import build_capability_profile
from app.learning import build_learning_candidates


class AgentRunConflict(ValueError):
    """The requested transition conflicts with durable run state."""


class AgentRunService:
    RUN_TYPE = "personalized_training_program"

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def propose_training_program(
        self,
        *,
        user_id: str,
        topic: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        clean_topic = (topic or "").strip()
        existing = self.repository.get_agent_run_by_idempotency(
            user_id=user_id,
            run_type=self.RUN_TYPE,
            idempotency_key=idempotency_key,
        )
        if existing:
            if existing["input"] != {"topic": clean_topic}:
                raise ValueError(
                    "Idempotency-Key 已用于不同的 Agent 工作流输入"
                )
            return existing
        rows = self.repository.get_capability_rows(user_id=user_id)
        capability = build_capability_profile(rows, topic=clean_topic or None)
        candidates = build_learning_candidates(capability)
        if not candidates:
            raise AgentRunConflict("暂无可生成训练方案的评分数据")
        profile = self.repository.get_user_profile(user_id=user_id) or {}
        proposal = {
            "schema_version": "training-program-proposal-v1",
            "target_role": profile.get("target_role") or "目标岗位",
            "topic": clean_topic,
            "answered_questions": capability["summary"]["answered_questions"],
            "candidates": candidates,
            "interview_create_url": "/interviews",
        }
        return self.repository.create_agent_run(
            user_id=user_id,
            run_type=self.RUN_TYPE,
            idempotency_key=idempotency_key,
            input_payload={"topic": clean_topic},
            proposal=proposal,
        )

    def inspect(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        run = self.repository.get_agent_run(user_id=user_id, run_id=run_id)
        if run:
            run["events"] = self._events(run)
        return run

    def list_runs(self, *, user_id: str) -> list[dict[str, object]]:
        runs = self.repository.list_agent_runs(user_id=user_id)
        for run in runs:
            run["events"] = self._events(run)
        return runs

    def inspect_for_admin(self, *, run_id: str) -> dict[str, object] | None:
        run = self.repository.get_agent_run_for_admin(run_id=run_id)
        if run:
            # Input/proposal/result are authoritative user-owned records; the
            # administrator endpoint exposes lifecycle metadata only.
            run.pop("input", None)
            run.pop("proposal", None)
            run.pop("result", None)
            for step in run.get("steps", []):
                if isinstance(step, dict):
                    step.pop("result", None)
            run["events"] = self._events(run)
        return run

    def confirm(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        claim_owner = str(uuid4())
        claim = self.repository.claim_agent_run_command(
            user_id=user_id,
            run_id=run_id,
            claim_owner=claim_owner,
        )
        if claim is None:
            return None
        if claim["state"] == "claimed":
            try:
                result = self.repository.complete_training_program_command(
                    user_id=user_id,
                    run_id=run_id,
                    claim_owner=claim_owner,
                )
            except Exception:
                self.repository.fail_agent_run_command(
                    user_id=user_id,
                    run_id=run_id,
                    claim_owner=claim_owner,
                    error_code="command_failed",
                )
                raise
            if result is None:
                raise AgentRunConflict("Agent 命令步骤领取已失效")
        elif claim["state"] == "busy":
            raise AgentRunConflict("Agent 工作流正在由其他执行者处理")
        return self.inspect(user_id=user_id, run_id=run_id)

    def retry(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        run = self.repository.get_agent_run(user_id=user_id, run_id=run_id)
        if not run:
            return None
        if run["status"] != "failed":
            raise AgentRunConflict("只有失败的工作流可重试")
        return self.confirm(user_id=user_id, run_id=run_id)

    def cancel(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        run = self.repository.cancel_agent_run(user_id=user_id, run_id=run_id)
        if run and run["status"] not in {"cancelled", "completed"}:
            raise AgentRunConflict("工作流已开始执行，不能取消")
        if run:
            run["events"] = self._events(run)
        return run

    def recover_stale(self, *, stale_seconds: int = 300) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=max(30, stale_seconds))
        return self.repository.recover_stale_agent_steps(
            stale_before=threshold.isoformat()
        )

    @staticmethod
    def _events(run: dict[str, object]) -> list[dict[str, object]]:
        events: list[dict[str, object]] = [
            {"event": "planned", "run_id": run["run_id"]}
        ]
        if run["status"] == "awaiting_confirmation":
            events.append({"event": "waiting_confirmation", "run_id": run["run_id"]})
        for step in run.get("steps", []):
            if not isinstance(step, dict):
                continue
            if step["status"] in {"claimed", "completed", "failed"}:
                events.append({
                    "event": "step_started",
                    "run_id": run["run_id"],
                    "step_id": step["step_id"],
                    "step_key": step["step_key"],
                })
            if step["status"] == "completed":
                events.append({
                    "event": "step_completed",
                    "run_id": run["run_id"],
                    "step_id": step["step_id"],
                    "step_key": step["step_key"],
                })
        terminal = {
            "completed": "done",
            "failed": "failed",
            "cancelled": "cancelled",
        }.get(str(run["status"]))
        if terminal:
            events.append({"event": terminal, "run_id": run["run_id"]})
        return events
