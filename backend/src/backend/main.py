"""
FastAPI application for the TanStack AI HITL Demo.

This module provides:
- POST /api/chat: Start or continue a chat stream
- GET /health: Health check endpoint
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import AgentRunResultEvent, DeferredToolRequests
from structlog.contextvars import bound_contextvars
from tanstack_pydantic_ai import TanStackAIAdapter
from tanstack_pydantic_ai.shared.sse import encode_done

from .agent import get_agent
from .continuations import ContinuationPayload, get_continuation_hub
from .db import get_db_connection
from .deps import Deps
from .logging import configure_logging, get_logger
from .settings import get_settings
from .store import get_artifact_store, get_run_store

# Get settings
settings = get_settings()
configure_logging()
logger = get_logger(__name__)

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
continuation_hub = get_continuation_hub()

KEEPALIVE_INTERVAL_SECONDS = 15.0


class ContinuationRequest(BaseModel):
    run_id: str
    approvals: dict[str, bool | dict[str, Any]] = Field(default_factory=dict)
    tool_results: dict[str, Any] = Field(default_factory=dict)


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
        with bound_contextvars(run_id=run_id):
            try:
                agent = get_agent()
            except Exception:
                logger.exception("Failed to construct agent")
                raise

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
                event_stream = adapter.build_event_stream()
                model_name = adapter.run_input.model or settings.llm_model or "unknown"

                def _usage_from_result(result: Any) -> dict[str, int] | None:
                    if result is None:
                        return None
                    try:
                        usage_data = result.usage()
                    except Exception:
                        return None
                    if not usage_data:
                        return None

                    def _get_usage_value(*names: str) -> int | None:
                        for name in names:
                            if isinstance(usage_data, dict) and name in usage_data:
                                return int(usage_data[name])
                            if hasattr(usage_data, name):
                                return int(getattr(usage_data, name))
                        return None

                    prompt_tokens = _get_usage_value(
                        "prompt_tokens", "promptTokens", "input_tokens", "inputTokens"
                    )
                    completion_tokens = _get_usage_value(
                        "completion_tokens",
                        "completionTokens",
                        "output_tokens",
                        "outputTokens",
                    )
                    total_tokens = _get_usage_value("total_tokens", "totalTokens")

                    if prompt_tokens is None or completion_tokens is None:
                        return None
                    if total_tokens is None:
                        total_tokens = prompt_tokens + completion_tokens

                    return {
                        "promptTokens": prompt_tokens,
                        "completionTokens": completion_tokens,
                        "totalTokens": total_tokens,
                    }

                try:
                    current_adapter = adapter
                    while True:
                        captured_result = None
                        is_deferred = False

                        async def capturing_native_events() -> AsyncIterator[Any]:
                            nonlocal captured_result, is_deferred
                            async for event in current_adapter.run_stream_native():
                                if isinstance(event, AgentRunResultEvent):
                                    captured_result = event.result
                                    output = getattr(event.result, "output", None)
                                    is_deferred = isinstance(
                                        output, DeferredToolRequests
                                    )
                                yield event

                        async for chunk in event_stream.transform_stream(
                            capturing_native_events(),
                            model_name=model_name,
                            usage_provider=lambda: _usage_from_result(captured_result),
                        ):
                            if chunk.type == "done" and is_deferred:
                                continue
                            yield event_stream.encode_event(chunk).encode("utf-8")

                        if not is_deferred:
                            break

                        while True:
                            payload = await continuation_hub.wait(
                                run_id, timeout=KEEPALIVE_INTERVAL_SECONDS
                            )
                            if payload is None:
                                yield b": keep-alive\n\n"
                                continue
                            if not payload.approvals and not payload.tool_results:
                                continue
                            break

                        continuation_body = json.dumps(
                            {
                                "run_id": run_id,
                                "approvals": payload.approvals,
                                "tool_results": payload.tool_results,
                            }
                        ).encode("utf-8")
                        current_adapter = TanStackAIAdapter.from_request(
                            agent=agent,
                            body=continuation_body,
                            accept=accept,
                            deps=deps,
                            store=store,
                        )
                finally:
                    await continuation_hub.clear(run_id)
                yield encode_done().encode("utf-8")

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


@app.post("/api/continuation")
async def post_continuation(payload: ContinuationRequest) -> dict:
    """
    Accept approval/tool results and resume the open SSE stream (Pattern A).
    """
    if not payload.run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    if not payload.approvals and not payload.tool_results:
        raise HTTPException(
            status_code=400, detail="approvals or tool_results must be provided"
        )

    await continuation_hub.push(
        payload.run_id,
        ContinuationPayload(
            approvals=payload.approvals, tool_results=payload.tool_results
        ),
    )
    return {"status": "ok"}


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
