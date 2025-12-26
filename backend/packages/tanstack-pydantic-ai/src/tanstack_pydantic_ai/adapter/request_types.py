"""
Request types for TanStack AI protocol.

Defines the input format expected from TanStack AI frontends.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallFunction(BaseModel):
    """Function details in a tool call."""

    name: str
    arguments: str  # JSON string


class ToolCallPart(BaseModel):
    """A tool call in the TanStack AI format."""

    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class UIMessage(BaseModel):
    """A message in the TanStack AI format."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str | None = None
    name: str | None = None
    toolCalls: list[ToolCallPart] | None = None
    toolCallId: str | None = None


class RequestData(BaseModel):
    """
    Request data from TanStack AI frontend.

    This is the protocol-specific input format that the adapter
    transforms into pydantic-ai arguments.
    """

    # NOTE: For stateful continuation (HITL), the frontend may send only
    # {run_id, approvals/tool_results}. In that case, message history is loaded
    # from the server-side store, so `messages` must be optional.
    messages: list[UIMessage] = Field(default_factory=list)
    model: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    # For continuation after deferred tools
    run_id: str | None = None
    tool_results: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, bool | dict[str, Any]] = Field(default_factory=dict)
