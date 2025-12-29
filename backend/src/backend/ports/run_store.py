"""
Port definition for run state storage.
"""

from __future__ import annotations

from typing import Protocol

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelMessage
from tanstack_pydantic_ai.shared.store import RunState


class RunStorePort(Protocol):
    """Interface for storing run state across requests."""

    def get(self, run_id: str) -> RunState | None: ...

    def set_messages(
        self, run_id: str, messages: list[ModelMessage], model: str | None
    ) -> RunState: ...

    def set_pending(
        self, run_id: str, pending: DeferredToolRequests | None, model: str | None
    ) -> RunState: ...

    def clear(self, run_id: str) -> None: ...
