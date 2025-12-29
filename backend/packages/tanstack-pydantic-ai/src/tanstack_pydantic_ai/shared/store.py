"""
Run state storage for stateful continuation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


class InMemoryRunStore(RunStorePort):
    """
    In-memory storage for agent run states.

    Used for stateful continuation in HITL (Human-in-the-Loop) flows.
    In production, replace with Redis or database-backed implementation.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def get(self, run_id: str) -> RunState | None:
        """Get run state by ID."""
        return self._runs.get(run_id)

    def set(self, run_id: str, state: RunState) -> None:
        """Set run state."""
        self._runs[run_id] = state

    def upsert(self, run_id: str, model: str | None) -> RunState:
        """Get or create run state."""
        state = self._runs.get(run_id)
        if state is None:
            state = RunState(model=model)
            self._runs[run_id] = state
        elif model is not None:
            state.model = model
        return state

    def set_messages(
        self,
        run_id: str,
        messages: list[ModelMessage],
        model: str | None,
    ) -> RunState:
        """Save message history for a run."""
        state = self.upsert(run_id, model)
        state.messages = messages
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
