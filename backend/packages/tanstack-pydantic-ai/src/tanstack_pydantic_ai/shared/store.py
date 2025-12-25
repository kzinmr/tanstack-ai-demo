"""
Run state storage for stateful continuation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic_ai import DeferredToolRequests, ModelMessage


@dataclass
class RunState:
    """State for a single agent run."""

    messages: List[ModelMessage] = field(default_factory=list)
    pending: Optional[DeferredToolRequests] = None
    model: Optional[str] = None


class InMemoryRunStore:
    """
    In-memory storage for agent run states.

    Used for stateful continuation in HITL (Human-in-the-Loop) flows.
    In production, replace with Redis or database-backed implementation.
    """

    def __init__(self) -> None:
        self._runs: Dict[str, RunState] = {}

    def get(self, run_id: str) -> Optional[RunState]:
        """Get run state by ID."""
        return self._runs.get(run_id)

    def set(self, run_id: str, state: RunState) -> None:
        """Set run state."""
        self._runs[run_id] = state

    def upsert(self, run_id: str, model: Optional[str]) -> RunState:
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
        messages: List[ModelMessage],
        model: Optional[str],
    ) -> RunState:
        """Save message history for a run."""
        state = self.upsert(run_id, model)
        state.messages = messages
        return state

    def set_pending(
        self,
        run_id: str,
        pending: Optional[DeferredToolRequests],
        model: Optional[str],
    ) -> RunState:
        """Save pending deferred tool requests."""
        state = self.upsert(run_id, model)
        state.pending = pending
        return state

    def clear(self, run_id: str) -> None:
        """Remove run state."""
        self._runs.pop(run_id, None)
