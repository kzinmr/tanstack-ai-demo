"""
TanStack AI adapter for pydantic-ai.

Implements the UIAdapter pattern for TanStack AI protocol integration.
Supports stateful continuation for deferred tools (HITL flows).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
)

from pydantic import TypeAdapter
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.output import OutputDataT
from pydantic_ai.tools import AgentDepsT

from ..shared.chunks import StreamChunk
from ..shared.sse import encode_done
from ..shared.store import InMemoryRunStore
from ._event_stream import TanStackEventStream
from .request_types import RequestData, UIMessage

# Type adapter for parsing request data
request_data_ta = TypeAdapter(RequestData)


OnCompleteFunc = Callable[["AgentRunResult"], Any] | None

try:
    from pydantic_ai.run import AgentRunResult
except ImportError:
    AgentRunResult = Any  # type: ignore


@dataclass
class TanStackAIAdapter(Generic[AgentDepsT, OutputDataT]):
    """
    UI adapter for TanStack AI protocol.

    This adapter implements the UIAdapter pattern from pydantic-ai,
    providing:
    - Request parsing (build_run_input)
    - Message format conversion (load_messages, dump_messages)
    - Agent execution (run_stream_native, run_stream)
    - SSE encoding (encode_stream)
    - Stateful continuation for deferred tools (HITL)

    Stateful Continuation (recommended):
        When `store` is provided, the adapter saves message history after each run.
        Continuation requests only need `run_id + tool_results/approvals`.

    Stateless Continuation:
        When `store` is None, continuation requests must include full `messages`.

    Usage with FastAPI:
        ```python
        from fastapi import FastAPI, Request
        from fastapi.responses import StreamingResponse
        from tanstack_pydantic_ai import TanStackAIAdapter, InMemoryRunStore

        app = FastAPI()
        agent = Agent(...)
        store = InMemoryRunStore()  # For stateful continuation

        @app.post("/api/chat")
        async def chat(request: Request):
            adapter = TanStackAIAdapter.from_request(
                agent, await request.body(), store=store
            )
            return StreamingResponse(
                adapter.streaming_response(),
                headers=dict(adapter.response_headers),
            )
        ```
    """

    agent: Agent[AgentDepsT, OutputDataT]
    run_input: RequestData
    accept: Optional[str] = None
    deps: Optional[AgentDepsT] = None
    store: Optional[InMemoryRunStore] = None

    # ─────────────────────────────────────────────────────────────────
    # Factory methods
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def from_request(
        cls,
        agent: Agent[AgentDepsT, OutputDataT],
        body: bytes,
        *,
        accept: Optional[str] = None,
        deps: Optional[AgentDepsT] = None,
        store: Optional[InMemoryRunStore] = None,
    ) -> "TanStackAIAdapter[AgentDepsT, OutputDataT]":
        """
        Create adapter from HTTP request body.

        Args:
            agent: The pydantic-ai Agent instance
            body: Raw request body bytes
            accept: Optional Accept header value
            deps: Optional agent dependencies
            store: Optional run store for stateful continuation

        Note:
            If run_id is not provided in the request, a new one is generated.
            The run_id is used to identify the run for continuation requests.
        """
        run_input = cls.build_run_input(body)

        # Ensure run_id is set (generate if not provided)
        if not run_input.run_id:
            run_input = run_input.model_copy(update={"run_id": uuid.uuid4().hex})

        return cls(
            agent=agent,
            run_input=run_input,
            accept=accept,
            deps=deps,
            store=store,
        )

    @classmethod
    def build_run_input(cls, body: bytes) -> RequestData:
        """Build TanStack AI run input from request body."""
        return request_data_ta.validate_json(body)

    @property
    def run_id(self) -> str:
        """
        The run ID for this adapter.

        This ID is used in StreamChunk.id and for continuation requests.
        Clients should use this ID when calling /continue.
        """
        return self.run_input.run_id or ""

    # ─────────────────────────────────────────────────────────────────
    # Event stream builder
    # ─────────────────────────────────────────────────────────────────

    def build_event_stream(self) -> TanStackEventStream[AgentDepsT, OutputDataT]:
        """Build TanStack event stream transformer."""
        return TanStackEventStream(
            run_input=self.run_input,
            accept=self.accept,
        )

    # ─────────────────────────────────────────────────────────────────
    # Message conversion
    # ─────────────────────────────────────────────────────────────────

    @cached_property
    def messages(self) -> List[ModelMessage]:
        """Pydantic AI messages from the TanStack AI run input."""
        return self.load_messages(self.run_input.messages)

    @classmethod
    def load_messages(cls, messages: Sequence[UIMessage]) -> List[ModelMessage]:
        """
        Transform TanStack AI messages into pydantic-ai messages.

        Handles:
        - system -> SystemPromptPart in ModelRequest
        - user -> UserPromptPart in ModelRequest
        - assistant -> TextPart/ToolCallPart in ModelResponse
        - tool -> ToolReturnPart in ModelRequest
        """
        result: List[ModelMessage] = []

        for msg in messages:
            if msg.role == "system":
                result.append(
                    ModelRequest(parts=[SystemPromptPart(content=msg.content or "")])
                )
            elif msg.role == "user":
                result.append(
                    ModelRequest(parts=[UserPromptPart(content=msg.content or "")])
                )
            elif msg.role == "assistant":
                parts: List[Any] = []
                if msg.content:
                    parts.append(TextPart(content=msg.content))
                if msg.toolCalls:
                    for tc in msg.toolCalls:
                        parts.append(
                            ToolCallPart(
                                tool_name=tc.function.name,
                                args=json.loads(tc.function.arguments),
                                tool_call_id=tc.id,
                            )
                        )
                if parts:
                    result.append(ModelResponse(parts=parts))
            elif msg.role == "tool":
                if msg.toolCallId:
                    result.append(
                        ModelRequest(
                            parts=[
                                ToolReturnPart(
                                    tool_name=msg.name or "unknown",
                                    content=msg.content or "",
                                    tool_call_id=msg.toolCallId,
                                )
                            ]
                        )
                    )

        return result

    @classmethod
    def dump_messages(cls, messages: Sequence[ModelMessage]) -> List[UIMessage]:
        """
        Transform pydantic-ai messages into TanStack AI messages.

        Used when returning conversation history to the frontend.
        """
        result: List[UIMessage] = []

        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, SystemPromptPart):
                        result.append(UIMessage(role="system", content=part.content))
                    elif isinstance(part, UserPromptPart):
                        if isinstance(part.content, str):
                            result.append(UIMessage(role="user", content=part.content))
                    elif isinstance(part, ToolReturnPart):
                        content = part.content
                        if not isinstance(content, str):
                            content = json.dumps(content, ensure_ascii=False)
                        result.append(
                            UIMessage(
                                role="tool",
                                content=content,
                                toolCallId=part.tool_call_id,
                                name=part.tool_name,
                            )
                        )
            elif isinstance(msg, ModelResponse):
                text_parts = []
                tool_calls = []
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        text_parts.append(part.content)
                    elif isinstance(part, ToolCallPart):
                        from .request_types import (
                            ToolCallFunction,
                            ToolCallPart as TCPart,
                        )

                        tool_calls.append(
                            TCPart(
                                id=part.tool_call_id or "",
                                function=ToolCallFunction(
                                    name=part.tool_name,
                                    arguments=json.dumps(part.args, ensure_ascii=False),
                                ),
                            )
                        )
                result.append(
                    UIMessage(
                        role="assistant",
                        content="".join(text_parts) if text_parts else None,
                        toolCalls=tool_calls if tool_calls else None,
                    )
                )

        return result

    # ─────────────────────────────────────────────────────────────────
    # Agent execution
    # ─────────────────────────────────────────────────────────────────

    @property
    def user_prompt(self) -> str:
        """Extract user prompt from the last user message."""
        for msg in reversed(self.run_input.messages):
            if msg.role == "user" and msg.content:
                return msg.content
        return ""

    @property
    def message_history(self) -> List[ModelMessage]:
        """
        Get message history for agent run.

        For continuation requests with stateful store:
            Loads history from store using run_id.

        For new requests or stateless mode:
            Uses messages from request (excluding last user message).

        Raises:
            ValueError: If continuation requested but run_id not found in store.
        """
        # Stateful continuation: load from store
        if self.is_continuation and self.store and self.run_id:
            stored = self.store.get(self.run_id)
            if stored is None:
                raise ValueError(f"Unknown run_id: {self.run_id}")
            # pydantic-ai expects "unprocessed tool calls" to be present in the
            # message history when deferred_tool_results are provided. In HITL
            # flows, we may have stored the pending deferred tool requests
            # separately (stored.pending). If the message history doesn't include
            # those tool calls, inject them so continuation can match approvals/
            # tool_results to tool_call_id.
            messages = list(stored.messages)

            pending = getattr(stored, "pending", None)
            if pending is not None:
                existing_tool_call_ids: set[str] = set()
                for msg in messages:
                    if isinstance(msg, ModelResponse):
                        for part in msg.parts:
                            if isinstance(part, ToolCallPart) and part.tool_call_id:
                                existing_tool_call_ids.add(part.tool_call_id)

                injected_parts: List[ToolCallPart] = []

                def _inject_from(parts: Any) -> None:
                    for p in parts or []:
                        tool_call_id = getattr(p, "tool_call_id", None)
                        if not tool_call_id or tool_call_id in existing_tool_call_ids:
                            continue
                        injected_parts.append(
                            ToolCallPart(
                                tool_name=getattr(p, "tool_name", "unknown"),
                                args=getattr(p, "args", {}) or {},
                                tool_call_id=tool_call_id,
                            )
                        )
                        existing_tool_call_ids.add(tool_call_id)

                # DeferredToolRequests usually has .approvals and .calls
                _inject_from(getattr(pending, "approvals", None))
                _inject_from(getattr(pending, "calls", None))

                if injected_parts:
                    messages.append(ModelResponse(parts=injected_parts))

            return messages

        # Stateless: build from request messages
        messages = self.messages
        if messages and isinstance(messages[-1], ModelRequest):
            # Check if it's a user message - exclude from history
            parts = messages[-1].parts
            if parts and isinstance(parts[0], UserPromptPart):
                return messages[:-1]
        return messages

    @property
    def is_continuation(self) -> bool:
        """Check if this is a continuation request (has tool results or approvals)."""
        return bool(self.run_input.tool_results or self.run_input.approvals)

    async def run_stream_native(self) -> AsyncIterator[Any]:
        """
        Run the agent and yield native pydantic-ai events.

        This provides the raw event stream before transformation.
        Also saves results to store for stateful continuation.
        """
        from pydantic_ai import AgentRunResultEvent

        run_id = self.run_id
        model = self.run_input.model

        def _agent_has_output_validators() -> bool:
            """
            pydantic-ai forbids passing a custom run `output_type` when the Agent
            has output validators. We detect validators via common internal/public
            attributes across pydantic-ai versions.
            """
            for attr in ("output_validators", "_output_validators"):
                validators = getattr(self.agent, attr, None)
                if validators:
                    return True
            return False

        kwargs: Dict[str, Any] = {
            "message_history": self.message_history,
        }
        # Only pass output_type when it's safe to do so (i.e. no output validators).
        # Prefer configuring Agent(output_type=...) at construction time.
        if not _agent_has_output_validators():
            kwargs["output_type"] = [str, DeferredToolRequests]
        if model:
            kwargs["model"] = model
        if self.deps is not None:
            kwargs["deps"] = self.deps

        # Handle continuation with deferred tool results
        if self.is_continuation:
            deferred = DeferredToolResults(
                approvals=self.run_input.approvals,
                calls=self.run_input.tool_results,
            )
            kwargs["deferred_tool_results"] = deferred
            # For continuation, use empty prompt
            prompt = ""
        else:
            prompt = self.user_prompt

        async for event in self.agent.run_stream_events(prompt, **kwargs):
            # Capture AgentRunResultEvent and save to store
            if self.store and isinstance(event, AgentRunResultEvent):
                result = event.result
                # Save message history for continuation
                self.store.set_messages(run_id, result.all_messages(), model)
                # Save pending deferred tools if any
                if isinstance(result.output, DeferredToolRequests):
                    self.store.set_pending(run_id, result.output, model)
                else:
                    self.store.set_pending(run_id, None, model)

            yield event

    async def run_stream(
        self,
        *,
        on_complete: OnCompleteFunc = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Run the agent and yield TanStack StreamChunks.

        Args:
            on_complete: Optional callback when agent run completes
        """
        from pydantic_ai import AgentRunResultEvent

        event_stream = self.build_event_stream()
        model_name = self.run_input.model or "unknown"
        captured_result = None

        # Create wrapper to capture result while yielding events
        async def capturing_native_events() -> AsyncIterator[Any]:
            nonlocal captured_result
            async for event in self.run_stream_native():
                if isinstance(event, AgentRunResultEvent):
                    captured_result = event.result
                yield event

        async for chunk in event_stream.transform_stream(
            capturing_native_events(),
            model_name=model_name,
        ):
            yield chunk

        # Handle on_complete callback if provided
        if on_complete is not None and captured_result is not None:
            callback_result = on_complete(captured_result)
            if hasattr(callback_result, "__await__"):
                await callback_result

    async def encode_stream(
        self,
        chunks: AsyncIterator[StreamChunk],
    ) -> AsyncIterator[bytes]:
        """
        Encode StreamChunks as SSE data frames.

        Transforms StreamChunk objects into SSE-formatted bytes.
        """
        event_stream = self.build_event_stream()
        async for chunk in chunks:
            yield event_stream.encode_event(chunk).encode("utf-8")
        yield encode_done().encode("utf-8")

    # ─────────────────────────────────────────────────────────────────
    # High-level response helpers
    # ─────────────────────────────────────────────────────────────────

    @property
    def response_headers(self) -> Mapping[str, str]:
        """Response headers for SSE streaming."""
        return self.build_event_stream().response_headers

    async def streaming_response(
        self,
        *,
        on_complete: OnCompleteFunc = None,
    ) -> AsyncIterator[bytes]:
        """
        Generate complete SSE streaming response.

        This is the main entry point for generating HTTP streaming responses.
        Combines run_stream() and encode_stream() into a single async generator.
        """
        event_stream = self.build_event_stream()

        async for chunk in self.run_stream(on_complete=on_complete):
            yield event_stream.encode_event(chunk).encode("utf-8")

        yield encode_done().encode("utf-8")
