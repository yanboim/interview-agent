"""API 层的同步执行辅助函数，统一取得应用级 SyncExecutor。"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from app.api.runtime import get_runtime

P = ParamSpec("P")
R = TypeVar("R")


async def run_sync(
    function: Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Dispatch one synchronous application or infrastructure call."""
    return await get_runtime().sync_executor.run(function, *args, **kwargs)
