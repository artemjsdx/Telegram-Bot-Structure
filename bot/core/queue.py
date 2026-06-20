"""
Serial request queue: exactly one AI call runs at a time.

FavoriteAPI returns KEY_BUSY (301) when two requests share a key concurrently,
so every provider call funnels through a single background worker. Each job is a
zero-arg coroutine factory; enqueue() awaits and returns its result (or re-raises
its exception), preserving normal call semantics for the caller.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

Factory = Callable[[], Awaitable[Any]]


class QueueManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background worker. Call once from post_init."""
        if self._worker and not self._worker.done():
            return
        self._queue = asyncio.Queue()
        self._worker = asyncio.create_task(self._run(), name="ai-queue-worker")
        log.info("Request queue worker started.")

    async def stop(self) -> None:
        """Cancel the worker (graceful shutdown)."""
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def enqueue(self, factory: Factory) -> Any:
        """
        Schedule a coroutine factory to run serially and await its result.
        Falls back to inline execution if the worker was never started.
        """
        if self._queue is None:
            return await factory()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        await self._queue.put((factory, fut))
        return await fut

    async def _run(self) -> None:
        assert self._queue is not None
        while True:
            factory, fut = await self._queue.get()
            try:
                result = await factory()
                if not fut.done():
                    fut.set_result(result)
            except Exception as e:
                if not fut.done():
                    fut.set_exception(e)
            finally:
                self._queue.task_done()


# Module-level singleton shared across handlers.
queue = QueueManager()
