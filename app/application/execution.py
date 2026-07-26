import asyncio
from collections.abc import Callable
from functools import partial
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class SyncExecutor:
    """Run synchronous use cases without blocking the async event loop."""

    async def run(
        self,
        function: Callable[P, R],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        return await asyncio.to_thread(partial(function, *args, **kwargs))
