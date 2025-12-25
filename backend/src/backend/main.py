"""
FastAPI application for the TanStack AI HITL Demo.

This module provides:
- POST /api/chat: Start a new chat stream
- POST /api/chat/continue: Continue after HITL approval/client tool execution
- GET /health: Health check endpoint
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from tanstack_pydantic_ai import InMemoryRunStore, TanStackAIAdapter

from .agent import agent
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


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    """
    Start a new chat stream.

    Request body should contain:
    - messages: List of chat messages
    - model: (optional) Model override

    Returns SSE stream with TanStack AI compatible chunks.
    """
    async with get_db_connection() as conn:
        deps = Deps(conn=conn)
        adapter = TanStackAIAdapter.from_request(
            agent=agent,
            body=await request.body(),
            accept=request.headers.get("accept"),
            deps=deps,
            store=store,
        )
        return StreamingResponse(
            adapter.streaming_response(),
            headers=dict(adapter.response_headers),
        )


@app.post("/api/chat/continue")
async def chat_continue(request: Request) -> StreamingResponse:
    """
    Continue a chat after HITL approval or client tool execution.

    Request body should contain:
    - run_id: The run ID from the previous stream
    - approvals: (optional) Map of tool_call_id -> true/false for approval
    - tool_results: (optional) Map of tool_call_id -> result for client tools

    Example approval request:
    {
        "run_id": "abc123",
        "approvals": {"tool_call_id_1": true}
    }

    Example client tool result:
    {
        "run_id": "abc123",
        "tool_results": {"tool_call_id_2": {"filename": "result.csv", "rowCount": 100}}
    }

    Returns SSE stream continuing from where it left off.
    """
    async with get_db_connection() as conn:
        deps = Deps(conn=conn)
        adapter = TanStackAIAdapter.from_request(
            agent=agent,
            body=await request.body(),
            accept=request.headers.get("accept"),
            deps=deps,
            store=store,
        )
        return StreamingResponse(
            adapter.streaming_response(),
            headers=dict(adapter.response_headers),
        )


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
