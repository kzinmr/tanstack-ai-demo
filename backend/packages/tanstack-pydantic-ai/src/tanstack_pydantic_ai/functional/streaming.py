"""
Core streaming logic for TanStack AI integration with pydantic-ai.

This module provides framework-agnostic streaming functionality.
No FastAPI or web framework dependencies.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
)

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.run import AgentRunResult

from ..shared.chunks import (
    ApprovalObj,
    ApprovalRequestedStreamChunk,
    ContentStreamChunk,
    DoneStreamChunk,
    ErrorObj,
    ErrorStreamChunk,
    StreamChunk,
    ThinkingStreamChunk,
    ToolCall,
    ToolCallFunction,
    ToolCallStreamChunk,
    ToolInputAvailableStreamChunk,
    ToolResultStreamChunk,
)
from ..shared.sse import now_ms


class StreamState:
    """Mutable state for tracking stream accumulation."""

    def __init__(self, run_id: str, model_name: str):
        self.run_id = run_id
        self.model_name = model_name
        self.text_accumulator: Dict[int, str] = {}
        self.thinking_accumulator: Dict[int, str] = {}
        self.tool_call_index = 0


def handle_stream_event(
    event: Any,
    state: StreamState,
) -> List[StreamChunk]:
    """
    Map pydantic-ai stream events to TanStack StreamChunks.

    Handles:
    - PartStartEvent / PartDeltaEvent for text and thinking content
    - FunctionToolCallEvent for tool calls
    - FunctionToolResultEvent for tool results
    """
    chunks: List[StreamChunk] = []
    ts = now_ms()
    run_id = state.run_id
    model_name = state.model_name

    # Handle PartStartEvent - initialize accumulators with initial content
    if isinstance(event, PartStartEvent):
        if isinstance(event.part, TextPart):
            state.text_accumulator[event.index] = event.part.content
            if event.part.content:
                chunks.append(
                    ContentStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=ts,
                        content=event.part.content,
                        delta=event.part.content,
                        role="assistant",
                    )
                )
        elif isinstance(event.part, ThinkingPart):
            state.thinking_accumulator[event.index] = event.part.content
            if event.part.content:
                chunks.append(
                    ThinkingStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=ts,
                        content=event.part.content,
                        delta=event.part.content,
                    )
                )

    # Handle PartDeltaEvent - accumulate text/thinking deltas
    elif isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            delta_text = event.delta.content_delta
            idx = event.index
            prev = state.text_accumulator.get(idx, "")
            new_content = prev + delta_text
            state.text_accumulator[idx] = new_content
            chunks.append(
                ContentStreamChunk(
                    id=run_id,
                    model=model_name,
                    timestamp=ts,
                    content=new_content,
                    delta=delta_text,
                    role="assistant",
                )
            )
        elif isinstance(event.delta, ThinkingPartDelta):
            # ThinkingPartDelta may have None content_delta (signature-only)
            if event.delta.content_delta:
                delta_text = event.delta.content_delta
                idx = event.index
                prev = state.thinking_accumulator.get(idx, "")
                new_content = prev + delta_text
                state.thinking_accumulator[idx] = new_content
                chunks.append(
                    ThinkingStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=ts,
                        content=new_content,
                        delta=delta_text,
                    )
                )

    # Handle FunctionToolCallEvent - emit tool call chunk
    elif isinstance(event, FunctionToolCallEvent):
        part: ToolCallPart = event.part
        chunks.append(
            ToolCallStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=ts,
                index=state.tool_call_index,
                toolCall=ToolCall(
                    id=part.tool_call_id,
                    function=ToolCallFunction(
                        name=part.tool_name,
                        arguments=json.dumps(
                            part.args if isinstance(part.args, dict) else part.args,
                            ensure_ascii=False,
                        ),
                    ),
                ),
            )
        )
        state.tool_call_index += 1

    # Handle FunctionToolResultEvent - emit tool result chunk
    elif isinstance(event, FunctionToolResultEvent):
        if isinstance(event.result, ToolReturnPart):
            content = event.result.content
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            chunks.append(
                ToolResultStreamChunk(
                    id=run_id,
                    model=model_name,
                    timestamp=ts,
                    toolCallId=event.result.tool_call_id,
                    content=content,
                )
            )

    return chunks


def _emit_deferred_chunks(
    run_id: str,
    model_name: str,
    pending: DeferredToolRequests,
) -> List[StreamChunk]:
    """
    Generate approval/input-available chunks for deferred tool calls.

    Note: ToolCallStreamChunk is NOT emitted here because it was already
    emitted in real-time via FunctionToolCallEvent during streaming.
    """
    chunks: List[StreamChunk] = []
    ts = now_ms()

    for part in pending.approvals:
        chunks.append(
            ApprovalRequestedStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=ts,
                toolCallId=part.tool_call_id,
                toolName=part.tool_name,
                input=part.args,
                approval=ApprovalObj(id=uuid.uuid4().hex),
            )
        )

    for part in pending.calls:
        chunks.append(
            ToolInputAvailableStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=ts,
                toolCallId=part.tool_call_id,
                toolName=part.tool_name,
                input=part.args,
            )
        )

    return chunks


class _ResultHolder:
    """Internal holder for lazily-created future."""

    def __init__(self) -> None:
        self._future: Optional[asyncio.Future[AgentRunResult]] = None

    def ensure_future(self) -> asyncio.Future[AgentRunResult]:
        """Create future if not exists (must be called from async context)."""
        if self._future is None:
            self._future = asyncio.get_running_loop().create_future()
        return self._future

    async def get_result(self) -> AgentRunResult:
        """Get the result from the future."""
        if self._future is None:
            raise RuntimeError("Stream has not been started")
        return await self._future


@dataclass
class StreamResult:
    """
    Result from stream_chat() or stream_continue().

    Provides both streaming chunks and final result access.

    Usage:
        stream = stream_chat(agent, "Hello")
        async for chunk in stream:
            print(chunk)
        # After iteration completes:
        result = await stream.result()
        messages = result.all_messages()
        output = result.output  # str | DeferredToolRequests
    """

    _run_id: str
    _model_name: str
    _chunks_gen: AsyncGenerator[StreamChunk, None]
    _result_holder: _ResultHolder = field(default_factory=_ResultHolder)

    @property
    def run_id(self) -> str:
        """The unique run ID for this stream."""
        return self._run_id

    @property
    def model_name(self) -> str:
        """The model name used for this stream."""
        return self._model_name

    def __aiter__(self):
        return self

    async def __anext__(self) -> StreamChunk:
        return await self._chunks_gen.__anext__()

    async def result(self) -> AgentRunResult:
        """Get the final AgentRunResult after streaming completes."""
        return await self._result_holder.get_result()


def stream_chat(
    agent: Agent,
    user_prompt: str,
    *,
    message_history: Optional[List[ModelMessage]] = None,
    model: Optional[str] = None,
    run_id: Optional[str] = None,
) -> StreamResult:
    """
    Stream chat response from agent.

    Returns StreamResult that:
    - Yields StreamChunks via async iteration
    - Provides AgentRunResult via await result()

    Args:
        agent: The pydantic-ai Agent instance
        user_prompt: The user's message
        message_history: Optional conversation history
        model: Optional model override
        run_id: Optional run ID (auto-generated if not provided)
    """
    run_id = run_id or uuid.uuid4().hex
    model_name = model or "unknown"
    result_holder = _ResultHolder()

    async def generate_chunks() -> AsyncGenerator[StreamChunk, None]:
        state = StreamState(run_id, model_name)
        result = None
        result_future = result_holder.ensure_future()

        try:

            def _agent_has_output_validators() -> bool:
                # See adapter/_adapter.py for rationale.
                for attr in ("output_validators", "_output_validators"):
                    validators = getattr(agent, attr, None)
                    if validators:
                        return True
                return False

            kwargs: Dict[str, Any] = {
                "message_history": message_history or [],
            }
            if not _agent_has_output_validators():
                kwargs["output_type"] = [str, DeferredToolRequests]
            if model is not None:
                kwargs["model"] = model

            async for event in agent.run_stream_events(user_prompt, **kwargs):
                # Handle stream events and emit chunks
                for chunk in handle_stream_event(event, state):
                    yield chunk

                # Capture the final result
                if isinstance(event, AgentRunResultEvent):
                    result = event.result

            # After stream completes, process final result
            if result is not None:
                output = result.output

                if isinstance(output, DeferredToolRequests):
                    # Emit deferred chunks
                    for chunk in _emit_deferred_chunks(run_id, model_name, output):
                        yield chunk
                    yield DoneStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=now_ms(),
                        finishReason="tool_calls",
                    )
                else:
                    yield DoneStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=now_ms(),
                        finishReason="stop",
                    )

                # Set result future
                result_future.set_result(result)

        except Exception as exc:
            yield ErrorStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=now_ms(),
                error=ErrorObj(message=str(exc)),
            )
            yield DoneStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=now_ms(),
                finishReason="stop",
            )
            result_future.set_exception(exc)

    return StreamResult(
        _run_id=run_id,
        _model_name=model_name,
        _chunks_gen=generate_chunks(),
        _result_holder=result_holder,
    )


def stream_continue(
    agent: Agent,
    deferred_tool_results: DeferredToolResults,
    *,
    message_history: List[ModelMessage],
    model: Optional[str] = None,
    run_id: Optional[str] = None,
) -> StreamResult:
    """
    Continue chat after deferred tool execution.

    Returns StreamResult that:
    - Yields StreamChunks via async iteration
    - Provides AgentRunResult via await result()

    Args:
        agent: The pydantic-ai Agent instance
        deferred_tool_results: Results from deferred tool execution
        message_history: Conversation history (required for continuation)
        model: Optional model override
        run_id: Optional run ID (auto-generated if not provided)
    """
    run_id = run_id or uuid.uuid4().hex
    model_name = model or "unknown"
    result_holder = _ResultHolder()

    async def generate_chunks() -> AsyncGenerator[StreamChunk, None]:
        state = StreamState(run_id, model_name)
        result = None
        result_future = result_holder.ensure_future()

        try:

            def _agent_has_output_validators() -> bool:
                # See adapter/_adapter.py for rationale.
                for attr in ("output_validators", "_output_validators"):
                    validators = getattr(agent, attr, None)
                    if validators:
                        return True
                return False

            kwargs: Dict[str, Any] = {
                "message_history": message_history,
                "deferred_tool_results": deferred_tool_results,
            }
            if not _agent_has_output_validators():
                kwargs["output_type"] = [str, DeferredToolRequests]
            if model is not None:
                kwargs["model"] = model

            async for event in agent.run_stream_events("", **kwargs):
                # Handle stream events and emit chunks
                for chunk in handle_stream_event(event, state):
                    yield chunk

                # Capture the final result
                if isinstance(event, AgentRunResultEvent):
                    result = event.result

            # After stream completes, process final result
            if result is not None:
                output = result.output

                if isinstance(output, DeferredToolRequests):
                    # Emit deferred chunks
                    for chunk in _emit_deferred_chunks(run_id, model_name, output):
                        yield chunk
                    yield DoneStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=now_ms(),
                        finishReason="tool_calls",
                    )
                else:
                    yield DoneStreamChunk(
                        id=run_id,
                        model=model_name,
                        timestamp=now_ms(),
                        finishReason="stop",
                    )

                # Set result future
                result_future.set_result(result)

        except Exception as exc:
            yield ErrorStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=now_ms(),
                error=ErrorObj(message=str(exc)),
            )
            yield DoneStreamChunk(
                id=run_id,
                model=model_name,
                timestamp=now_ms(),
                finishReason="stop",
            )
            result_future.set_exception(exc)

    return StreamResult(
        _run_id=run_id,
        _model_name=model_name,
        _chunks_gen=generate_chunks(),
        _result_holder=result_holder,
    )


# Helper for building message history from simple role/content pairs
def build_message_history(
    messages: List[Tuple[Literal["user", "assistant"], str]],
) -> List[ModelMessage]:
    """
    Build pydantic-ai message history from role/content tuples.

    Args:
        messages: List of (role, content) tuples

    Returns:
        List of ModelMessage objects
    """
    history: List[ModelMessage] = []
    for role, content in messages:
        if role == "user":
            history.append(ModelRequest([UserPromptPart(content=content)]))
        else:
            history.append(ModelResponse([TextPart(content=content)]))
    return history
