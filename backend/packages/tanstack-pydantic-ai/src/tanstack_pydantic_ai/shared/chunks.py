"""
TanStack AI StreamChunk types.

These types define the SSE streaming protocol for TanStack AI frontends.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

StreamChunkType = Literal[
    "content",
    "thinking",
    "tool_call",
    "tool_result",
    "tool-input-available",
    "approval-requested",
    "error",
    "done",
]


class BaseStreamChunk(BaseModel):
    id: str
    model: str
    timestamp: int
    type: StreamChunkType


class ContentStreamChunk(BaseStreamChunk):
    type: Literal["content"] = "content"
    content: str
    delta: str
    role: Literal["assistant"] | None = None


class ThinkingStreamChunk(BaseStreamChunk):
    type: Literal["thinking"] = "thinking"
    content: str
    delta: str


class ToolCallFunction(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class ToolCallStreamChunk(BaseStreamChunk):
    type: Literal["tool_call"] = "tool_call"
    index: int
    toolCall: ToolCall


class ToolResultStreamChunk(BaseStreamChunk):
    type: Literal["tool_result"] = "tool_result"
    toolCallId: str
    content: str


class ToolInputAvailableStreamChunk(BaseStreamChunk):
    type: Literal["tool-input-available"] = "tool-input-available"
    toolCallId: str
    toolName: str
    input: Any


class ApprovalObj(BaseModel):
    id: str
    needsApproval: Literal[True] = True


class ApprovalRequestedStreamChunk(BaseStreamChunk):
    type: Literal["approval-requested"] = "approval-requested"
    toolCallId: str
    toolName: str
    input: Any
    approval: ApprovalObj


class ErrorObj(BaseModel):
    message: str
    code: str | None = None


class ErrorStreamChunk(BaseStreamChunk):
    type: Literal["error"] = "error"
    error: ErrorObj


class UsageObj(BaseModel):
    completionTokens: int
    promptTokens: int
    totalTokens: int


class DoneStreamChunk(BaseStreamChunk):
    type: Literal["done"] = "done"
    finishReason: Literal["stop", "length", "tool_calls", "content_filter"]
    usage: UsageObj | None = None


StreamChunk = (
    ContentStreamChunk
    | ThinkingStreamChunk
    | ToolCallStreamChunk
    | ToolResultStreamChunk
    | ToolInputAvailableStreamChunk
    | ApprovalRequestedStreamChunk
    | ErrorStreamChunk
    | DoneStreamChunk
)
