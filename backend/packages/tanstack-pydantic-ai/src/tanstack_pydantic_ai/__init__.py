"""
TanStack AI integration for pydantic-ai.

This package provides the UIAdapter API for TanStack AI protocol integration:

- TanStackAIAdapter, TanStackEventStream classes
- Follows pydantic-ai UIAdapter pattern
- Built-in SSE encoding and response helpers

Shared components from tanstack_pydantic_ai.shared:
- StreamChunk types for the TanStack AI protocol
- InMemoryRunStore for stateful continuation
- SSE encoding utilities
"""

# UIAdapter API
from .adapter import (
    RequestData,
    TanStackAIAdapter,
    TanStackEventStream,
    UIMessage,
)

# Shared: Chunk types
from .shared.chunks import (
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

# Shared: SSE utilities
from .shared.sse import dump_chunk, encode_chunk, encode_done, now_ms, sse_data

# Shared: Store
from .shared.store import InMemoryRunStore, RunState

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
    # Store
    "InMemoryRunStore",
    "RunState",
    # SSE utilities
    "dump_chunk",
    "encode_chunk",
    "encode_done",
    "now_ms",
    "sse_data",
    # UIAdapter API
    "RequestData",
    "TanStackAIAdapter",
    "TanStackEventStream",
    "UIMessage",
]
