"""
UIAdapter API for TanStack AI integration.

This module provides a class-based UIAdapter pattern for TanStack AI protocol.

Usage:
    ```python
    from tanstack_pydantic_ai.adapter import TanStackAIAdapter, TanStackEventStream

    # In FastAPI endpoint
    adapter = TanStackAIAdapter.from_request(agent, body, store=store)
    return StreamingResponse(
        adapter.streaming_response(),
        headers=dict(adapter.response_headers),
    )
    ```
"""

from ._adapter import TanStackAIAdapter
from ._event_stream import TanStackEventStream
from .request_types import (
    RequestData,
    ToolCallFunction,
    ToolCallPart,
    UIMessage,
)

__all__ = [
    "TanStackAIAdapter",
    "TanStackEventStream",
    "RequestData",
    "ToolCallFunction",
    "ToolCallPart",
    "UIMessage",
]
