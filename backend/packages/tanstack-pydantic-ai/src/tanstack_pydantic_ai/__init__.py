"""
TanStack AI integration for pydantic-ai.

Public exports are intentionally minimal to keep the API stable:
- TanStackAIAdapter, TanStackEventStream
- StreamChunk, StreamChunkType
- InMemoryRunStore, RunState

Low-level request/chunk models and SSE helpers remain available via submodules
but are not part of the public, semver-stable API.
"""

from .adapter import TanStackAIAdapter, TanStackEventStream
from .shared.chunks import StreamChunk, StreamChunkType
from .shared.store import InMemoryRunStore, RunState

__all__ = [
    # Store
    "InMemoryRunStore",
    "RunState",
    # UIAdapter API
    "TanStackAIAdapter",
    "TanStackEventStream",
    # Chunk types
    "StreamChunk",
    "StreamChunkType",
]
