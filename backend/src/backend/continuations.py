"""
In-memory continuation hub for pattern A (single-stream HITL).

Keeps a per-run queue of approvals/tool results so the streaming
request can await human input and resume in the same SSE connection.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContinuationPayload:
    approvals: dict[str, bool | dict[str, Any]] = field(default_factory=dict)
    tool_results: dict[str, Any] = field(default_factory=dict)


class ContinuationHub:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[ContinuationPayload]] = {}
        self._lock = asyncio.Lock()

    async def _get_queue(self, run_id: str) -> asyncio.Queue[ContinuationPayload]:
        async with self._lock:
            return self._queues.setdefault(run_id, asyncio.Queue())

    async def wait(
        self, run_id: str, *, timeout: float | None = None
    ) -> ContinuationPayload | None:
        queue = await self._get_queue(run_id)
        try:
            if timeout is None:
                return await queue.get()
            return await asyncio.wait_for(queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def push(self, run_id: str, payload: ContinuationPayload) -> None:
        queue = await self._get_queue(run_id)
        queue.put_nowait(payload)

    async def clear(self, run_id: str) -> None:
        async with self._lock:
            self._queues.pop(run_id, None)


_continuation_hub = ContinuationHub()


def get_continuation_hub() -> ContinuationHub:
    return _continuation_hub
