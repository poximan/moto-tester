from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class SnapshotHub:
    """Produce una sola captura y la comparte con todos los clientes."""

    def __init__(
        self,
        interval_s: float,
        producer: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        self._interval_s = max(float(interval_s), 0.2)
        self._producer = producer
        self._condition = asyncio.Condition()
        self._revision = 0
        self._snapshot: dict[str, Any] | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="snapshot-hub")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def wait_next(self, after_revision: int) -> tuple[int, dict[str, Any]]:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._snapshot is not None and self._revision > after_revision
            )
            return self._revision, self._snapshot

    async def _run(self) -> None:
        while True:
            snapshot = await self._producer()
            async with self._condition:
                self._snapshot = snapshot
                self._revision += 1
                self._condition.notify_all()
            await asyncio.sleep(self._interval_s)
