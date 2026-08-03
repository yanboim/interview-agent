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
    """派发一次同步的应用或基础设施调用到工作线程。

    统一从运行时取 ``SyncExecutor``，把阻塞型数据库工作移出事件循环，
    而不是在各路由内散落地把同步用例交给线程池。

    返回:
        被调用函数的返回值。
    """
    return await get_runtime().sync_executor.run(function, *args, **kwargs)
