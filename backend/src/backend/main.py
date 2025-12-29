"""
FastAPI application for the TanStack AI HITL Demo.

This module provides:
- POST /api/chat: Start or continue a chat stream
- GET /health: Health check endpoint
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from tanstack_pydantic_ai import TanStackAIAdapter
from structlog.contextvars import bind_contextvars, clear_contextvars

from .agent import get_agent
from .db import get_db_connection
from .deps import Deps
from .logging import configure_logging, get_logger
from .settings import get_settings
from .store import get_artifact_store, get_run_store

# Get settings
settings = get_settings()
configure_logging()

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

# Run store for HITL continuation (swap via settings)
store = get_run_store()

logger = get_logger(__name__)


def _sse_headers() -> dict[str, str]:
    """Standard SSE response headers."""
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


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
    import json

    body = await request.body()
    accept = request.headers.get("accept")

    # Parse run_id from body for Deps (used to scope artifacts).
    # Ensure the same run_id is used by both Deps and the adapter.
    try:
        body_json = json.loads(body) if body else {}
    except json.JSONDecodeError:
        body_json = None

    # Ensure run_id is present (generate if missing) for the adapter and deps.
    run_id = body_json.get("run_id") if isinstance(body_json, dict) else None

    if not run_id:
        run_id = uuid.uuid4().hex

    if isinstance(body_json, dict):
        body_json["run_id"] = run_id
        body = json.dumps(body_json).encode("utf-8")

    async def stream() -> AsyncIterator[bytes]:
        # IMPORTANT: keep DB connection open for the entire stream duration.
        # Otherwise tool execution (especially after HITL approval) can fail with
        # "connection is closed" when the request handler returns.
        bind_contextvars(run_id=run_id)
        try:
            agent = get_agent()
        except Exception:
            logger.exception("Failed to construct agent", run_id=run_id)
            clear_contextvars()
            raise

        try:
            async with get_db_connection() as conn:
                deps = Deps(
                    conn=conn, run_id=run_id, artifact_store=get_artifact_store()
                )
                adapter = TanStackAIAdapter.from_request(
                    agent=agent,
                    body=body,
                    accept=accept,
                    deps=deps,
                    store=store,
                )
                async for chunk in adapter.streaming_response():
                    yield chunk
        finally:
            clear_contextvars()

    return StreamingResponse(
        TanStackAIAdapter.stream_with_error_handling(
            stream(), model=settings.llm_model, run_id=run_id
        ),
        headers=_sse_headers(),
    )


@app.get("/api/data/{run_id}/{artifact_id:path}")
async def get_csv_data(
    run_id: str,
    artifact_id: str,
    mode: str = Query(default="preview", pattern="^(preview|download)$"),
) -> dict:
    """
    Get CSV export data by run_id and artifact ID.

    This endpoint is called by the frontend after receiving a tool-input-available
    chunk for the export_csv tool. The artifact_id is included in the tool args,
    and the run_id is used to scope the data. Use mode=download to return a
    signed URL when the artifact store supports it.

    Args:
        run_id: The run ID that produced this dataset
        artifact_id: The artifact identifier

    Returns:
        JSON with rows/columns or a signed download URL
    """
    artifact_store = get_artifact_store()

    if mode == "download":
        download = artifact_store.get_download(run_id, artifact_id)
        if download is not None:
            return {
                "mode": "signed-url",
                "download_url": download.url,
                "expires_in_seconds": download.expires_in_seconds,
                "method": download.method,
                "headers": download.headers,
            }

    preview = artifact_store.get_preview(run_id, artifact_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Artifact not found or expired")

    return {
        "mode": "inline",
        "rows": preview.rows,
        "columns": preview.columns,
        "original_row_count": preview.original_row_count,
        "exported_row_count": preview.exported_row_count,
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
