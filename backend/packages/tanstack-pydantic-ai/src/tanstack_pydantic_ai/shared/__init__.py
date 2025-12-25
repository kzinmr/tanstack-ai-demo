"""
Shared components for TanStack AI integration.

This module contains common types and utilities used by both
the functional API and UIAdapter API.
"""

from .chunks import (
    ApprovalObj,
    ApprovalRequestedStreamChunk,
    BaseStreamChunk,
    ContentStreamChunk,
    DoneStreamChunk,
    ErrorObj,
    ErrorStreamChunk,
    StreamChunk,
    StreamChunkType,
    ThinkingStreamChunk,
    ToolCall,
    ToolCallFunction,
    ToolCallStreamChunk,
    ToolInputAvailableStreamChunk,
    ToolResultStreamChunk,
    UsageObj,
)
from .sse import dump_chunk, encode_chunk, encode_done, now_ms, sse_data
from .store import InMemoryRunStore, RunState

__all__ = [
    # Chunk types
    "ApprovalObj",
    "ApprovalRequestedStreamChunk",
    "BaseStreamChunk",
    "ContentStreamChunk",
    "DoneStreamChunk",
    "ErrorObj",
    "ErrorStreamChunk",
    "StreamChunk",
    "StreamChunkType",
    "ThinkingStreamChunk",
    "ToolCall",
    "ToolCallFunction",
    "ToolCallStreamChunk",
    "ToolInputAvailableStreamChunk",
    "ToolResultStreamChunk",
    "UsageObj",
    # SSE utilities
    "dump_chunk",
    "encode_chunk",
    "encode_done",
    "now_ms",
    "sse_data",
    # Store
    "InMemoryRunStore",
    "RunState",
]
