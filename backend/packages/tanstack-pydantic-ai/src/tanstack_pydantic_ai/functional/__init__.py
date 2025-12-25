"""
Functional API for TanStack AI streaming.

This module provides function-based streaming interface for pydantic-ai agents.

Usage:
    ```python
    from tanstack_pydantic_ai.functional import stream_chat, stream_continue

    stream = stream_chat(agent, "Hello")
    async for chunk in stream:
        print(chunk)
    result = await stream.result()
    ```
"""

from .streaming import (
    StreamResult,
    StreamState,
    build_message_history,
    handle_stream_event,
    stream_chat,
    stream_continue,
)

__all__ = [
    "StreamResult",
    "StreamState",
    "build_message_history",
    "handle_stream_event",
    "stream_chat",
    "stream_continue",
]
