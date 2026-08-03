"""应用拥有的持久化 Agent 工作流生命周期。

把多步 Agent 动作（当前为个性化训练方案）的命令、确认、执行、重试、取消
建模为可恢复的持久化 run/step 记录。LangGraph 仅作为进程内编排细节，
真正的业务状态以 ``agent_runs``/``agent_steps`` 表为唯一来源。
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from app.capability import build_capability_profile
from app.learning import build_learning_candidates


class AgentRunRepository(Protocol):
    def get_agent_run_by_idempotency(self, **kwargs: Any) -> Any: ...
    def get_capability_rows(self, **kwargs: Any) -> Any: ...
    def get_user_profile(self, **kwargs: Any) -> Any: ...
    def create_agent_run(self, **kwargs: Any) -> Any: ...
    def get_agent_run(self, **kwargs: Any) -> Any: ...
    def get_agent_run_for_admin(self, **kwargs: Any) -> Any: ...
    def list_agent_runs(self, **kwargs: Any) -> Any: ...
    def claim_agent_run_command(self, **kwargs: Any) -> Any: ...
    def complete_training_program_command(self, **kwargs: Any) -> Any: ...
    def cancel_agent_run(self, **kwargs: Any) -> Any: ...
    def fail_agent_run_command(self, **kwargs: Any) -> Any: ...
    def recover_stale_agent_steps(self, **kwargs: Any) -> Any: ...


class AgentRunConflict(ValueError):
    """请求的状态转换与持久化 run 状态冲突。"""


class AgentRunService:
    """协调个性化训练方案工作流：提议、预览确认、持久化执行、恢复。

    所有命令都经幂等键与 claim_owner（所有者令牌）封闭：步骤领取是条件
    且带所有者，命令效果、重放结果与终态原子提交，任何模型/工具调用都
    在数据库事务之外。
    """

    RUN_TYPE = "personalized_training_program"

    def __init__(self, repository: AgentRunRepository) -> None:
        """注入持久化仓库（``ConversationStore`` 或测试替身）。"""
        self.repository = repository

    def propose_training_program(
        self,
        *,
        user_id: str,
        topic: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        """提议一份个性化训练方案（待用户确认），幂等。

        基于用户能力画像与学习候选生成方案预览。同一幂等键重复请求返回
        已有 run；但若幂等键已用于不同输入则报错。

        参数:
            user_id: 服务端解析的当前用户 ID。
            topic: 可选训练主题。
            idempotency_key: 客户端幂等键。

        返回:
            新建或复用的 run（含 ``proposal``）。

        异常:
            ValueError: 幂等键已用于不同的工作流输入。
            AgentRunConflict: 暂无可生成方案的评分数据。
        """
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
        """所有者查看单个 run，含派生的生命周期事件序列。

        参数:
            user_id: 当前用户 ID，用于所有者范围校验。
            run_id: 目标 run ID。

        返回:
            run 字典（附带 ``events``）；不存在或非本人所有时返回 ``None``。
        """
        run = self.repository.get_agent_run(user_id=user_id, run_id=run_id)
        if run:
            run["events"] = self._events(run)
        return run

    def list_runs(self, *, user_id: str) -> list[dict[str, object]]:
        """列出当前用户的所有 run，每项附带生命周期事件序列。"""
        runs = self.repository.list_agent_runs(user_id=user_id)
        for run in runs:
            run["events"] = self._events(run)
        return runs

    def inspect_for_admin(self, *, run_id: str) -> dict[str, object] | None:
        """管理员查看 run：仅暴露生命周期元数据，剥离用户私密正文。

        input/proposal/result 是用户拥有的权威记录，管理员端只展示状态与
        步骤元数据，不含输入、提案、结果正文，符合不可信/隐私边界。

        返回:
            剥离私密正文、附带 ``events`` 的 run；不存在时为 ``None``。
        """
        run = self.repository.get_agent_run_for_admin(run_id=run_id)
        if run:
            # Input/proposal/result 是用户拥有的权威记录；管理员端只暴露生命周期元数据。
            run.pop("input", None)
            run.pop("proposal", None)
            run.pop("result", None)
            for step in run.get("steps", []):
                if isinstance(step, dict):
                    step.pop("result", None)
            run["events"] = self._events(run)
        return run

    def confirm(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        """用户确认并执行已提议的工作流命令（claim_owner 所有者封闭）。

        用 claim_owner 领取命令步骤；成功则完成命令并落库结果，失败则
        把命令标记失败再上抛。这与持久化 run 共同保证命令效果原子提交、
        可安全重放。

        返回:
            含 ``events`` 的 run；不存在时为 ``None``。

        异常:
            AgentRunConflict: 命令步骤领取已失效，或工作流正由其他执行者处理。
        """
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
        """重试已失败的工作流（仅失败态可重试），复用确认/执行流程。

        异常:
            AgentRunConflict: run 不处于失败状态。
        """
        run = self.repository.get_agent_run(user_id=user_id, run_id=run_id)
        if not run:
            return None
        if run["status"] != "failed":
            raise AgentRunConflict("只有失败的工作流可重试")
        return self.confirm(user_id=user_id, run_id=run_id)

    def cancel(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        """取消工作流；仅在尚未执行（cancelled/completed 之外）时允许。

        异常:
            AgentRunConflict: 工作流已开始执行，不能取消。
        """
        run = self.repository.cancel_agent_run(user_id=user_id, run_id=run_id)
        if run and run["status"] not in {"cancelled", "completed"}:
            raise AgentRunConflict("工作流已开始执行，不能取消")
        if run:
            run["events"] = self._events(run)
        return run

    def recover_stale(self, *, stale_seconds: int = 300) -> int:
        """回收长时间卡在 ``claimed`` 的僵死步骤（崩溃恢复）。

        参数:
            stale_seconds: 视为僵死的时长下限，至少 30 秒。

        返回:
            本次回收的步骤数量。

        规则:
            仅由运维/定时任务调用，做安全的终态回收；不会自动接管可能
            仍在执行的慢所有者（自动 lease 接管被禁止）。
        """
        threshold = datetime.now(UTC) - timedelta(seconds=max(30, stale_seconds))
        return self.repository.recover_stale_agent_steps(
            stale_before=threshold.isoformat()
        )

    @staticmethod
    def _events(run: dict[str, object]) -> list[dict[str, object]]:
        """从 run/step 状态派生面向 SSE 的生命周期事件序列。

        只暴露 lifecycle 事件（planned/waiting_confirmation/step_*、终态），
        不携带用户输入、提案或结果正文，符合管理员/SSE 的安全边界。
        """
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
