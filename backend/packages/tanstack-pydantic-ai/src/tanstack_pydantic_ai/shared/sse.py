"""
SSE (Server-Sent Events) encoding utilities.
"""

from __future__ import annotations

import json
import time

from .chunks import StreamChunk


def now_ms() -> int:
    """Get current timestamp in milliseconds."""
    return int(time.time() * 1000)


def sse_data(payload: str) -> str:
    """Wrap payload in SSE data frame format."""
    return f"data: {payload}\n\n"


def dump_chunk(chunk: StreamChunk) -> str:
    """Serialize StreamChunk to JSON string.

    Uses by_alias=True to output camelCase field names (e.g., toolCallId)
    as required by the TanStack AI protocol.
    """
    return json.dumps(chunk.model_dump(by_alias=True), ensure_ascii=False)


def encode_chunk(chunk: StreamChunk) -> str:
    """Encode StreamChunk as SSE data frame."""
    return sse_data(dump_chunk(chunk))


def encode_done() -> str:
    """Encode SSE stream termination marker."""
    return sse_data("[DONE]")
