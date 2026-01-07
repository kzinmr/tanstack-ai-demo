"""
Run state storage for stateful continuation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from pydantic_ai import DeferredToolRequests, ModelMessage


@dataclass
class RunState:
    """State for a single agent run."""

    messages: list[ModelMessage] = field(default_factory=list)
    pending: DeferredToolRequests | None = None
    model: str | None = None


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

    def cleanup_expired(self) -> int: ...


class InMemoryRunStore(RunStorePort):
    """
    In-memory storage for agent run states.

    Used for stateful continuation in HITL (Human-in-the-Loop) flows.
    In production, replace with Redis or database-backed implementation.
    """

    def __init__(
        self,
        *,
        ttl_minutes: int | None = None,
        max_messages: int | None = None,
    ) -> None:
        self._runs: dict[str, RunState] = {}
        self._last_updated: dict[str, datetime] = {}
        self._ttl = (
            timedelta(minutes=ttl_minutes)
            if ttl_minutes is not None and ttl_minutes > 0
            else None
        )
        self._max_messages = max_messages if max_messages and max_messages > 0 else None

    def _touch(self, run_id: str) -> None:
        self._last_updated[run_id] = datetime.now()

    def _apply_max_messages(
        self, messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        if self._max_messages is None:
            return messages
        return messages[-self._max_messages :]

    def cleanup_expired(self) -> int:
        """Remove expired run states."""
        if self._ttl is None:
            return 0
        now = datetime.now()
        expired = [
            run_id
            for run_id, updated_at in self._last_updated.items()
            if now - updated_at > self._ttl
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)
            self._last_updated.pop(run_id, None)
        return len(expired)

    def get(self, run_id: str) -> RunState | None:
        """Get run state by ID."""
        self.cleanup_expired()
        return self._runs.get(run_id)

    def set(self, run_id: str, state: RunState) -> None:
        """Set run state."""
        self._runs[run_id] = state
        self._touch(run_id)

    def upsert(self, run_id: str, model: str | None) -> RunState:
        """Get or create run state."""
        self.cleanup_expired()
        state = self._runs.get(run_id)
        if state is None:
            state = RunState(model=model)
            self._runs[run_id] = state
        elif model is not None:
            state.model = model
        self._touch(run_id)
        return state

    def set_messages(
        self,
        run_id: str,
        messages: list[ModelMessage],
        model: str | None,
    ) -> RunState:
        """Save message history for a run."""
        state = self.upsert(run_id, model)
        state.messages = self._apply_max_messages(messages)
        return state

    def set_pending(
        self,
        run_id: str,
        pending: DeferredToolRequests | None,
        model: str | None,
    ) -> RunState:
        """Save pending deferred tool requests."""
        state = self.upsert(run_id, model)
        state.pending = pending
        return state

    def clear(self, run_id: str) -> None:
        """Remove run state."""
        self._runs.pop(run_id, None)
        self._last_updated.pop(run_id, None)
