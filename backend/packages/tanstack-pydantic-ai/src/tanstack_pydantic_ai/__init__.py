"""
TanStack AI integration for pydantic-ai.

This package provides two APIs for TanStack AI protocol integration:

1. Functional API (tanstack_pydantic_ai.functional):
   - stream_chat(), stream_continue() functions
   - Framework-agnostic, returns StreamResult

2. UIAdapter API (tanstack_pydantic_ai.adapter):
   - TanStackAIAdapter, TanStackEventStream classes
   - Follows pydantic-ai UIAdapter pattern
   - Built-in SSE encoding and response helpers

Both APIs use shared components from tanstack_pydantic_ai.shared:
   - StreamChunk types for the TanStack AI protocol
   - InMemoryRunStore for stateful continuation
   - SSE encoding utilities
"""

# Shared components
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
from .shared.sse import dump_chunk, encode_chunk, encode_done, now_ms, sse_data
from .shared.store import InMemoryRunStore, RunState

# Functional API
from .functional.streaming import (
    StreamResult,
    StreamState,
    build_message_history,
    handle_stream_event,
    stream_chat,
    stream_continue,
)

# UIAdapter API
from .adapter import (
    RequestData,
    TanStackAIAdapter,
    TanStackEventStream,
    UIMessage,
)

__all__ = [
    # Shared: Chunk types
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
    # Shared: Store
    "InMemoryRunStore",
    "RunState",
    # Shared: SSE utilities
    "dump_chunk",
    "encode_chunk",
    "encode_done",
    "now_ms",
    "sse_data",
    # Functional API
    "StreamResult",
    "StreamState",
    "build_message_history",
    "handle_stream_event",
    "stream_chat",
    "stream_continue",
    # UIAdapter API
    "RequestData",
    "TanStackAIAdapter",
    "TanStackEventStream",
    "UIMessage",
]
