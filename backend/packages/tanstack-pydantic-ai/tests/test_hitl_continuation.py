import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel

from tanstack_pydantic_ai import InMemoryRunStore, TanStackAIAdapter


async def _collect(stream: AsyncIterator[bytes]) -> list[bytes]:
    return [chunk async for chunk in stream]


def _parse_sse_frames(frames: list[bytes]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for frame in frames:
        text = frame.decode("utf-8")
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :].strip()
            if payload == "[DONE]":
                continue
            parsed.append(json.loads(payload))
    return parsed


def _make_agent() -> Agent[None, str | DeferredToolRequests]:
    model = TestModel(call_tools=["execute_query_readonly"])
    agent: Agent[None, str | DeferredToolRequests] = Agent(
        model,
        output_type=[str, DeferredToolRequests],
    )

    @agent.tool_plain(requires_approval=True)
    async def execute_query_readonly(sql: str) -> str:
        return "ok"

    return agent


def _build_adapter(
    agent: Agent[None, str | DeferredToolRequests],
    store: InMemoryRunStore,
    body: dict[str, Any],
) -> TanStackAIAdapter[None, str | DeferredToolRequests]:
    body_bytes = json.dumps(body).encode("utf-8")
    return TanStackAIAdapter.from_request(agent=agent, body=body_bytes, store=store)


def test_hitl_approval_flow_produces_tool_result() -> None:
    store = InMemoryRunStore()
    agent = _make_agent()

    adapter = _build_adapter(
        agent,
        store,
        {"messages": [{"role": "user", "content": "run"}], "model": "test"},
    )
    frames = asyncio.run(_collect(adapter.streaming_response()))
    chunks = _parse_sse_frames(frames)
    approval = next(chunk for chunk in chunks if chunk["type"] == "approval-requested")

    run_id = adapter.run_id
    tool_call_id = approval["toolCallId"]
    assert store.get(run_id) is not None

    adapter2 = _build_adapter(
        agent,
        store,
        {"run_id": run_id, "approvals": {tool_call_id: True}},
    )
    frames2 = asyncio.run(_collect(adapter2.streaming_response()))
    chunks2 = _parse_sse_frames(frames2)
    assert any(
        chunk["type"] == "tool_result" and chunk["toolCallId"] == tool_call_id
        for chunk in chunks2
    )


def test_hitl_rejection_flow_produces_tool_result() -> None:
    store = InMemoryRunStore()
    agent = _make_agent()

    adapter = _build_adapter(
        agent,
        store,
        {"messages": [{"role": "user", "content": "run"}], "model": "test"},
    )
    frames = asyncio.run(_collect(adapter.streaming_response()))
    chunks = _parse_sse_frames(frames)
    approval = next(chunk for chunk in chunks if chunk["type"] == "approval-requested")

    run_id = adapter.run_id
    tool_call_id = approval["toolCallId"]

    adapter2 = _build_adapter(
        agent,
        store,
        {"run_id": run_id, "approvals": {tool_call_id: False}},
    )
    frames2 = asyncio.run(_collect(adapter2.streaming_response()))
    chunks2 = _parse_sse_frames(frames2)

    denied = [
        chunk
        for chunk in chunks2
        if chunk["type"] == "tool_result" and chunk["toolCallId"] == tool_call_id
    ]
    assert denied
    assert "denied" in str(denied[0]["content"]).lower()


def test_message_history_prefers_store_when_run_id_present() -> None:
    store = InMemoryRunStore()
    agent = _make_agent()

    run_id = "run-1"
    stored_messages = [
        ModelRequest(parts=[UserPromptPart(content="run")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="execute_query_readonly",
                    args={"sql": "select 1"},
                    tool_call_id="call-1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="execute_query_readonly",
                    content="ok",
                    tool_call_id="call-1",
                )
            ]
        ),
    ]
    store.set_messages(run_id, stored_messages, model="test")

    adapter = _build_adapter(
        agent,
        store,
        {"run_id": run_id, "messages": [{"role": "user", "content": "next"}]},
    )

    assert adapter.message_history == stored_messages
