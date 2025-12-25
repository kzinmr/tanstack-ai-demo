"""
FastAPI application for the TanStack AI HITL Demo.

This module provides:
- POST /api/chat: Start or continue a chat stream
- GET /health: Health check endpoint
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from tanstack_pydantic_ai import InMemoryRunStore, TanStackAIAdapter
from tanstack_pydantic_ai.shared.chunks import (
    DoneStreamChunk,
    ErrorObj,
    ErrorStreamChunk,
)
from tanstack_pydantic_ai.shared.sse import encode_chunk, encode_done, now_ms

from .agent import get_agent
from .data_store import csv_data_store
from .db import get_db_connection
from .deps import Deps
from .settings import get_settings

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="TanStack AI HITL Demo",
    description="SQL Analysis Agent with Human-in-the-Loop",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for HITL continuation
store = InMemoryRunStore()

logger = logging.getLogger(__name__)


def _sse_headers() -> dict[str, str]:
    # Keep consistent with TanStackAIAdapter.response_headers
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


async def _stream_init_error(message: str) -> AsyncIterator[bytes]:
    """
    Produce a TanStack-compatible SSE stream for initialization errors.

    This keeps the frontend contract stable (SSE + [DONE]) even when the agent
    can't be constructed (e.g. missing API keys).
    """
    run_id = uuid.uuid4().hex
    model_name = settings.llm_model
    yield encode_chunk(
        ErrorStreamChunk(
            id=run_id,
            model=model_name,
            timestamp=now_ms(),
            error=ErrorObj(message=message),
        )
    ).encode("utf-8")
    yield encode_chunk(
        DoneStreamChunk(
            id=run_id,
            model=model_name,
            timestamp=now_ms(),
            finishReason="stop",
        )
    ).encode("utf-8")
    yield encode_done().encode("utf-8")


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    """
    Start or continue a chat stream.

    Request body should contain:
    - messages: List of chat messages
    - model: (optional) Model override
    - run_id: (optional) Run ID for continuation
    - approvals/tool_results: (optional) HITL continuation payload

    Returns SSE stream with TanStack AI compatible chunks.
    """
    body = await request.body()
    accept = request.headers.get("accept")

    async def stream() -> AsyncIterator[bytes]:
        # IMPORTANT: keep DB connection open for the entire stream duration.
        # Otherwise tool execution (especially after HITL approval) can fail with
        # "connection is closed" when the request handler returns.
        try:
            agent = get_agent()
        except Exception as exc:
            logger.exception("Failed to construct agent")
            async for b in _stream_init_error(str(exc)):
                yield b
            return

        try:
            async with get_db_connection() as conn:
                deps = Deps(conn=conn)
                adapter = TanStackAIAdapter.from_request(
                    agent=agent,
                    body=body,
                    accept=accept,
                    deps=deps,
                    store=store,
                )
                async for chunk in adapter.streaming_response():
                    yield chunk
        except Exception as exc:
            # Ensure we always emit a TanStack-compatible error chunk rather than
            # failing the stream silently.
            logger.exception("Unhandled error while streaming /api/chat")
            event_stream = TanStackAIAdapter.from_request(
                agent=agent,
                body=body,
                accept=accept,
                deps=None,
                store=store,
            ).build_event_stream()
            async for error_chunk in event_stream.on_error(exc):
                yield event_stream.encode_event(error_chunk).encode("utf-8")
            async for done_chunk in event_stream.after_stream():
                yield event_stream.encode_event(done_chunk).encode("utf-8")
            yield encode_done().encode("utf-8")

    return StreamingResponse(stream(), headers=_sse_headers())


@app.get("/api/data/{dataset:path}")
async def get_csv_data(dataset: str) -> dict:
    """
    Get CSV export data by dataset reference.

    This endpoint is called by the frontend after receiving a tool-input-available
    chunk for the export_csv tool. The dataset reference (e.g., "Out[1]") is
    included in the tool args.

    Args:
        dataset: The dataset reference (e.g., "Out[1]")

    Returns:
        JSON with rows, columns, and row count information
    """
    data = csv_data_store().get(dataset)
    if data is None:
        raise HTTPException(status_code=404, detail="Data not found or expired")

    return {
        "rows": data.rows,
        "columns": data.columns,
        "original_row_count": data.original_row_count,
        "exported_row_count": data.exported_row_count,
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": settings.llm_model,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
