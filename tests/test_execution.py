"""同步用例执行器（SyncExecutor）的测试。"""

import asyncio

from app.application.execution import SyncExecutor


def test_sync_executor_uses_shared_thread_boundary_and_preserves_arguments(
    monkeypatch,
) -> None:
    dispatched = []

    async def dispatch(function):
        dispatched.append(function)
        return function()

    monkeypatch.setattr(asyncio, "to_thread", dispatch)
    result = asyncio.run(
        SyncExecutor().run(
            lambda value, *, suffix: value + suffix,
            "transaction",
            suffix="-complete",
        )
    )

    assert result == "transaction-complete"
    assert len(dispatched) == 1
