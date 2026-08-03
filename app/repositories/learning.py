"""Learning, Agent run, confirmation, and coaching-memory persistence."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.database import (
    agent_action_confirmations,
    agent_runs,
    agent_steps,
    coaching_memories,
    interview_reviews,
    interviews,
    learning_tasks,
)


class LearningRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

    def create_learning_tasks(
        self,
        *,
        user_id: str,
        candidates: list[dict[str, str]],
        source_interview_id: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize()
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        with self.engine.begin() as connection:
            for candidate in candidates:
                existing = connection.execute(
                    select(learning_tasks.c.task_id).where(
                        learning_tasks.c.user_id == user_id,
                        learning_tasks.c.dimension
                        == candidate["dimension"],
                        learning_tasks.c.weakness
                        == candidate["weakness"],
                        learning_tasks.c.status != "completed",
                    )
                ).first()
                if existing:
                    continue
                connection.execute(
                    insert(learning_tasks).values(
                        task_id=str(uuid4()),
                        user_id=user_id,
                        source_interview_id=source_interview_id,
                        dimension=candidate["dimension"],
                        weakness=candidate["weakness"],
                        action=candidate["action"],
                        status="todo",
                        due_at=(now + timedelta(days=7)).isoformat(),
                        review_count=0,
                        next_review_at=(now + timedelta(days=1)).isoformat(),
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                )
        return self.list_learning_tasks(user_id=user_id)

    @staticmethod
    def _agent_run_payload(row: dict[str, object], steps: list[dict[str, object]]) -> dict[str, object]:
        payload = dict(row)
        for key in ("input_json", "proposal_json", "result_json"):
            raw = payload.pop(key, None)
            payload[key.removesuffix("_json")] = json.loads(str(raw)) if raw else None
        decoded_steps = []
        for item in steps:
            step = dict(item)
            raw_result = step.pop("result_json", None)
            step["result"] = json.loads(str(raw_result)) if raw_result else None
            decoded_steps.append(step)
        payload["steps"] = decoded_steps
        return payload

    def create_agent_run(
        self,
        *,
        user_id: str,
        run_type: str,
        idempotency_key: str,
        input_payload: dict[str, object],
        proposal: dict[str, object],
    ) -> dict[str, object]:
        """Persist a proposed workflow and its stable steps in one transaction."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        input_json = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        input_digest = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
        proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        run_id = str(uuid4())
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(agent_runs).values(
                    run_id=run_id, user_id=user_id, run_type=run_type,
                    status="awaiting_confirmation", idempotency_key=idempotency_key,
                    input_digest=input_digest, input_json=input_json,
                    proposal_json=proposal_json, created_at=now, updated_at=now,
                ))
                read_result = json.dumps(
                    {"candidate_count": len(proposal.get("candidates", []))},
                    ensure_ascii=False, separators=(",", ":"),
                )
                for step_key, step_type, status, result in (
                    ("plan", "read", "completed", read_result),
                    ("create_tasks", "command", "pending", None),
                ):
                    connection.execute(insert(agent_steps).values(
                        step_id=str(uuid4()), run_id=run_id, user_id=user_id,
                        step_key=step_key, step_type=step_type, status=status,
                        idempotency_key=f"{run_id}:{step_key}", input_digest=input_digest,
                        attempt_count=1 if status == "completed" else 0,
                        result_json=result, created_at=now, updated_at=now,
                    ))
        except IntegrityError:
            existing = self.get_agent_run_by_idempotency(
                user_id=user_id, run_type=run_type, idempotency_key=idempotency_key
            )
            if not existing or existing["input_digest"] != input_digest:
                raise ValueError("Idempotency-Key 已用于不同的 Agent 工作流输入")
            return existing
        return self.get_agent_run(user_id=user_id, run_id=run_id)  # type: ignore[return-value]

    def get_agent_run_by_idempotency(
        self, *, user_id: str, run_type: str, idempotency_key: str
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id,
                agent_runs.c.run_type == run_type,
                agent_runs.c.idempotency_key == idempotency_key,
            )).mappings().first()
            if not row:
                return None
            steps = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == row["run_id"]
            ).order_by(agent_steps.c.created_at)).mappings().all()
        return self._agent_run_payload(dict(row), [dict(item) for item in steps])

    def get_agent_run(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            )).mappings().first()
            if not row:
                return None
            steps = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.user_id == user_id,
            ).order_by(agent_steps.c.created_at)).mappings().all()
        return self._agent_run_payload(dict(row), [dict(item) for item in steps])

    def get_agent_run_for_admin(self, *, run_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.run_id == run_id
            )).mappings().first()
        if not row:
            return None
        return self.get_agent_run(
            user_id=str(row["user_id"]), run_id=str(row["run_id"])
        )

    def list_agent_runs(self, *, user_id: str) -> list[dict[str, object]]:
        self.initialize()
        with self.engine.connect() as connection:
            ids = connection.execute(select(agent_runs.c.run_id).where(
                agent_runs.c.user_id == user_id
            ).order_by(agent_runs.c.created_at.desc())).scalars().all()
        return [run for run_id in ids if (run := self.get_agent_run(user_id=user_id, run_id=str(run_id)))]

    def claim_agent_run_command(
        self, *, user_id: str, run_id: str, claim_owner: str
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            ).with_for_update()).mappings().first()
            if not row:
                return None
            if row["status"] in {"completed", "cancelled"}:
                return {"state": "replay", "status": str(row["status"])}
            if row["status"] not in {"awaiting_confirmation", "running", "failed"}:
                return {"state": "busy", "status": str(row["status"])}
            claimed = connection.execute(update(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.user_id == user_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status.in_(["pending", "failed"]),
            ).values(
                status="claimed", claim_owner=claim_owner, claimed_at=now,
                attempt_count=agent_steps.c.attempt_count + 1,
                error_code=None, updated_at=now,
            ))
            if claimed.rowcount != 1:
                return {"state": "busy", "status": str(row["status"])}
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id == run_id
            ).values(status="running", error_code=None, updated_at=now))
        return {"state": "claimed", "status": "running"}

    def complete_training_program_command(
        self, *, user_id: str, run_id: str, claim_owner: str
    ) -> dict[str, object] | None:
        """Apply the command and store its replay result atomically."""
        self.initialize()
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        with self.engine.begin() as connection:
            run = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            ).with_for_update()).mappings().first()
            if not run:
                return None
            if run["status"] == "completed":
                return json.loads(str(run["result_json"]))
            step = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).with_for_update()).mappings().first()
            if not step:
                return None
            proposal = json.loads(str(run["proposal_json"]))
            created_ids: list[str] = []
            for candidate in proposal["candidates"]:
                existing = connection.execute(select(learning_tasks.c.task_id).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.dimension == candidate["dimension"],
                    learning_tasks.c.weakness == candidate["weakness"],
                    learning_tasks.c.status != "completed",
                )).scalar_one_or_none()
                if existing:
                    created_ids.append(str(existing))
                    continue
                task_id = str(uuid4())
                connection.execute(insert(learning_tasks).values(
                    task_id=task_id, user_id=user_id,
                    dimension=candidate["dimension"], weakness=candidate["weakness"],
                    action=candidate["action"], status="todo",
                    due_at=(now + timedelta(days=7)).isoformat(), review_count=0,
                    next_review_at=(now + timedelta(days=1)).isoformat(),
                    created_at=now_iso, updated_at=now_iso,
                ))
                created_ids.append(task_id)
            result = {
                "task_ids": created_ids,
                "task_count": len(created_ids),
                "interview_create_url": "/interviews",
            }
            result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            completed = connection.execute(update(agent_steps).where(
                agent_steps.c.step_id == step["step_id"],
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).values(status="completed", result_json=result_json, updated_at=now_iso))
            if completed.rowcount != 1:
                raise RuntimeError("Agent 命令步骤领取已失效")
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id == run_id, agent_runs.c.status == "running"
            ).values(status="completed", result_json=result_json, updated_at=now_iso))
        return result

    def cancel_agent_run(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(update(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id,
                agent_runs.c.status.in_(["proposed", "awaiting_confirmation"]),
            ).values(status="cancelled", updated_at=now))
            if changed.rowcount:
                connection.execute(update(agent_steps).where(
                    agent_steps.c.run_id == run_id, agent_steps.c.status == "pending"
                ).values(status="skipped", updated_at=now))
        return self.get_agent_run(user_id=user_id, run_id=run_id)

    def fail_agent_run_command(
        self,
        *,
        user_id: str,
        run_id: str,
        claim_owner: str,
        error_code: str,
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            connection.execute(update(agent_steps).where(
                agent_steps.c.user_id == user_id,
                agent_steps.c.run_id == run_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).values(status="failed", error_code=error_code[:80], updated_at=now))
            connection.execute(update(agent_runs).where(
                agent_runs.c.user_id == user_id,
                agent_runs.c.run_id == run_id,
                agent_runs.c.status == "running",
            ).values(status="failed", error_code=error_code[:80], updated_at=now))

    def recover_stale_agent_steps(
        self, *, stale_before: str
    ) -> int:
        """Release abandoned claims; command effects are atomic and replay-safe."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            stale = connection.execute(select(agent_steps.c.run_id).where(
                agent_steps.c.status == "claimed",
                agent_steps.c.claimed_at < stale_before,
            )).scalars().all()
            if not stale:
                return 0
            released = connection.execute(update(agent_steps).where(
                agent_steps.c.status == "claimed",
                agent_steps.c.claimed_at < stale_before,
            ).values(
                status="pending", claim_owner=None, claimed_at=None,
                error_code="stale_claim_recovered", updated_at=now,
            ))
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id.in_(list(stale)), agent_runs.c.status == "running"
            ).values(status="failed", error_code="stale_claim_recovered", updated_at=now))
            return int(released.rowcount)

    def create_learning_plan_preview(
        self,
        *,
        user_id: str,
        topic: str,
        candidates: list[dict[str, str]],
        ttl_seconds: int = 600,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        payload = {
            "topic": topic.strip(),
            "candidates": candidates,
        }
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        confirmation_id = str(uuid4())
        expires_at = now + timedelta(seconds=max(60, min(ttl_seconds, 3600)))
        with self.engine.begin() as connection:
            connection.execute(
                insert(agent_action_confirmations).values(
                    confirmation_id=confirmation_id,
                    user_id=user_id,
                    action_type="create_learning_plan",
                    payload_json=payload_json,
                    payload_digest=hashlib.sha256(
                        payload_json.encode("utf-8")
                    ).hexdigest(),
                    status="pending",
                    expires_at=expires_at.isoformat(),
                    created_at=now.isoformat(),
                )
            )
        return {
            "confirmation_id": confirmation_id,
            "status": "awaiting_confirmation",
            "expires_at": expires_at.isoformat(),
            **payload,
        }

    def confirm_learning_plan(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "create_learning_plan",
                )
                .with_for_update()
            ).mappings().first()
            if not row:
                return None
            if row["status"] == "applied":
                return json.loads(str(row["result_json"]))
            if row["status"] != "pending":
                return {
                    "confirmation_id": confirmation_id,
                    "status": str(row["status"]),
                }
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                connection.execute(
                    update(agent_action_confirmations)
                    .where(
                        agent_action_confirmations.c.confirmation_id
                        == confirmation_id,
                        agent_action_confirmations.c.status == "pending",
                    )
                    .values(status="expired")
                )
                return {
                    "confirmation_id": confirmation_id,
                    "status": "expired",
                }
            payload_json = str(row["payload_json"])
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if digest != row["payload_digest"]:
                raise ValueError("学习计划确认内容摘要不匹配")
            payload = json.loads(payload_json)
            candidates = payload["candidates"]
            for candidate in candidates:
                existing = connection.execute(
                    select(learning_tasks.c.task_id).where(
                        learning_tasks.c.user_id == user_id,
                        learning_tasks.c.dimension == candidate["dimension"],
                        learning_tasks.c.weakness == candidate["weakness"],
                        learning_tasks.c.status != "completed",
                    )
                ).first()
                if existing:
                    continue
                connection.execute(
                    insert(learning_tasks).values(
                        task_id=str(uuid4()),
                        user_id=user_id,
                        dimension=candidate["dimension"],
                        weakness=candidate["weakness"],
                        action=candidate["action"],
                        status="todo",
                        due_at=(now + timedelta(days=7)).isoformat(),
                        review_count=0,
                        next_review_at=(now + timedelta(days=1)).isoformat(),
                        created_at=now.isoformat(),
                        updated_at=now.isoformat(),
                    )
                )
            tasks = [
                dict(item)
                for item in connection.execute(
                    select(learning_tasks)
                    .where(learning_tasks.c.user_id == user_id)
                    .order_by(
                        learning_tasks.c.status,
                        learning_tasks.c.due_at,
                        learning_tasks.c.created_at.desc(),
                    )
                ).mappings()
            ]
            result = {
                "confirmation_id": confirmation_id,
                "status": "applied",
                "tasks": tasks,
            }
            result_json = json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            claimed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.status == "pending",
                )
                .values(
                    status="applied",
                    result_json=result_json,
                    consumed_at=now.isoformat(),
                )
            )
            if claimed.rowcount != 1:
                raise RuntimeError("学习计划确认发生并发冲突")
            return result

    def create_public_search_preview(
        self,
        *,
        user_id: str,
        query: str,
        ttl_seconds: int = 600,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        payload_json = json.dumps(
            {"query": query},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        confirmation_id = str(uuid4())
        expires_at = now + timedelta(seconds=max(60, min(ttl_seconds, 3600)))
        with self.engine.begin() as connection:
            connection.execute(
                insert(agent_action_confirmations).values(
                    confirmation_id=confirmation_id,
                    user_id=user_id,
                    action_type="public_web_search",
                    payload_json=payload_json,
                    payload_digest=hashlib.sha256(
                        payload_json.encode("utf-8")
                    ).hexdigest(),
                    status="pending",
                    expires_at=expires_at.isoformat(),
                    created_at=now.isoformat(),
                )
            )
        return {
            "confirmation_id": confirmation_id,
            "status": "awaiting_confirmation",
            "expires_at": expires_at.isoformat(),
            "query": query,
        }

    def claim_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> dict[str, object] | None:
        """Atomically consume a pending search preview before network I/O."""
        self.initialize()
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(agent_action_confirmations).where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                )
            ).mappings().first()
            if not row:
                return None
            if row["status"] == "applied":
                if row["result_json"]:
                    return {
                        "status": "replay",
                        "result": json.loads(str(row["result_json"]))["result"],
                    }
                return {"status": "in_progress"}
            if row["status"] != "pending":
                return {"status": str(row["status"])}
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                connection.execute(
                    update(agent_action_confirmations)
                    .where(
                        agent_action_confirmations.c.confirmation_id
                        == confirmation_id,
                        agent_action_confirmations.c.status == "pending",
                    )
                    .values(status="expired")
                )
                return {"status": "expired"}
            payload_json = str(row["payload_json"])
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if digest != row["payload_digest"]:
                raise ValueError("联网查询确认内容摘要不匹配")
            claimed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.status == "pending",
                )
                .values(status="applied", consumed_at=now.isoformat())
            )
            if claimed.rowcount != 1:
                return {"status": "in_progress"}
            return {
                "status": "claimed",
                "query": json.loads(payload_json)["query"],
            }

    def complete_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
        result: str,
    ) -> None:
        self.initialize()
        result_json = json.dumps(
            {"result": result},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.engine.begin() as connection:
            completed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                    agent_action_confirmations.c.status == "applied",
                    agent_action_confirmations.c.result_json.is_(None),
                )
                .values(result_json=result_json)
            )
            if completed.rowcount != 1:
                raise RuntimeError("联网查询确认结果保存发生并发冲突")

    def cancel_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> None:
        self.initialize()
        with self.engine.begin() as connection:
            connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                    agent_action_confirmations.c.status == "applied",
                    agent_action_confirmations.c.result_json.is_(None),
                )
                .values(status="cancelled")
            )

    def list_learning_tasks(
        self,
        *,
        user_id: str,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(learning_tasks).where(
            learning_tasks.c.user_id == user_id
        )
        if status:
            statement = statement.where(learning_tasks.c.status == status)
        statement = statement.order_by(
            learning_tasks.c.status,
            learning_tasks.c.due_at,
            learning_tasks.c.created_at.desc(),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def create_coaching_memory(
        self,
        *,
        user_id: str,
        kind: str,
        content: str,
        source_type: str = "user",
        source_id: str | None = None,
        source_revision: int | None = None,
        expires_at: str | None = None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        memory_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(coaching_memories).values(
                    memory_id=memory_id,
                    user_id=user_id,
                    kind=kind,
                    content=content.strip(),
                    status="proposed",
                    source_type=source_type,
                    source_id=source_id,
                    source_revision=source_revision,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now,
                )
            )
            row = connection.execute(
                select(coaching_memories).where(
                    coaching_memories.c.memory_id == memory_id
                )
            ).mappings().one()
        return dict(row)

    def list_coaching_memories(
        self,
        *,
        user_id: str,
        status: str | None = None,
        context_ready_only: bool = False,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(coaching_memories).where(
            coaching_memories.c.user_id == user_id
        )
        if status:
            statement = statement.where(coaching_memories.c.status == status)
        statement = statement.order_by(coaching_memories.c.updated_at.desc())
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(statement).mappings()]
            if not context_ready_only:
                return rows
            ready = []
            for row in rows:
                if row["status"] != "confirmed":
                    continue
                expires_at = row.get("expires_at")
                if expires_at and datetime.fromisoformat(str(expires_at)) <= now:
                    continue
                if row["kind"] == "observation" and not self._memory_source_current(
                    connection, row
                ):
                    continue
                ready.append(row)
            return ready

    @staticmethod
    def _memory_source_current(connection, row: dict[str, object]) -> bool:
        source_type = str(row.get("source_type") or "")
        source_id = row.get("source_id")
        revision = row.get("source_revision")
        if source_type == "resume_analysis" and source_id:
            current = connection.execute(
                select(resume_analyses.c.revision, resume_analyses.c.status).where(
                    resume_analyses.c.analysis_id == source_id
                )
            ).first()
            return bool(current and current[1] == "ready" and current[0] == revision)
        if source_type == "interview_review" and source_id:
            current = connection.execute(
                select(
                    interview_reviews.c.confirmed_revision,
                    interview_reviews.c.status,
                ).where(interview_reviews.c.review_id == source_id)
            ).first()
            return bool(current and current[1] == "ready" and current[0] == revision)
        return source_type == "user"

    def update_coaching_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        action: str,
        content: str | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values: dict[str, object | None] = {"updated_at": now}
        if action == "confirm":
            values.update(status="confirmed", confirmed_at=now)
        elif action == "reject":
            values.update(status="rejected", confirmed_at=None)
        elif action == "correct":
            if not content or not content.strip():
                raise ValueError("记忆内容不能为空")
            values.update(
                content=content.strip(),
                status="proposed",
                confirmed_at=None,
                source_type="user",
                source_id=None,
                source_revision=None,
            )
        else:
            raise ValueError("未知记忆操作")
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(coaching_memories)
                .where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
                .values(**values)
            )
            if not changed.rowcount:
                return None
            row = connection.execute(
                select(coaching_memories).where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
            ).mappings().one()
        return dict(row)

    def delete_coaching_memory(self, *, user_id: str, memory_id: str) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            deleted = connection.execute(
                delete(coaching_memories).where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
            )
        return bool(deleted.rowcount)

    def update_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
        status: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        values: dict[str, object] = {
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if status is not None:
            values["status"] = status
        if due_at is not None:
            values["due_at"] = due_at
        with self.engine.begin() as connection:
            result = connection.execute(
                update(learning_tasks)
                .where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
                .values(**values)
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                select(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().one()
        return dict(row)

    def review_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
        outcome: str = "remembered",
        difficulty: int = 3,
    ) -> dict[str, object] | None:
        from app.learning import next_review_time

        self.initialize()
        if outcome not in {"remembered", "partial", "forgotten"}:
            raise ValueError("复习结果不合法")
        if not 1 <= difficulty <= 5:
            raise ValueError("难度必须在 1 到 5 之间")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            current = connection.execute(
                select(
                    learning_tasks.c.review_count,
                    learning_tasks.c.status,
                    learning_tasks.c.lapse_count,
                    learning_tasks.c.review_confidence,
                ).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().first()
            if not current:
                return None
            review_count = int(current["review_count"]) + 1
            lapse_count = int(current["lapse_count"] or 0) + (
                1 if outcome == "forgotten" else 0
            )
            previous_confidence = float(current["review_confidence"] or 0.5)
            confidence_delta = {
                "remembered": 0.15,
                "partial": -0.05,
                "forgotten": -0.2,
            }[outcome]
            confidence = min(1.0, max(0.1, previous_confidence + confidence_delta))
            connection.execute(
                update(learning_tasks)
                .where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
                .values(
                    review_count=review_count,
                    recall_outcome=outcome,
                    difficulty_rating=difficulty,
                    lapse_count=lapse_count,
                    review_confidence=confidence,
                    last_reviewed_at=now.isoformat(),
                    next_review_at=next_review_time(
                        review_count,
                        now=now,
                        outcome=outcome,
                        difficulty=difficulty,
                        lapse_count=lapse_count,
                        confidence=confidence,
                    ).isoformat(),
                    status=(
                        current["status"]
                        if current["status"] == "completed"
                        else "in_progress"
                    ),
                    updated_at=now.isoformat(),
                )
            )
            row = connection.execute(
                select(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().one()
        return dict(row)

    def delete_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
    ) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            )
        return bool(result.rowcount)
