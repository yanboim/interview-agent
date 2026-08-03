"""同步用例执行边界：统一把阻塞型数据库工作移出事件循环。"""

import asyncio
from collections.abc import Callable
from functools import partial
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class SyncExecutor:
    """在事件循环之外执行同步用例，避免阻塞异步路由。

    把阻塞型数据库工作统一放到工作线程，便于集中治理执行边界。
    """

    async def run(
        self,
        function: Callable[P, R],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        """在独立工作线程中执行同步函数并返回结果。

        参数:
            function: 同步可调用对象。
            *args / **kwargs: 透传给函数的位置与关键字参数。

        返回:
            函数的返回值。
        """
        return await asyncio.to_thread(partial(function, *args, **kwargs))
