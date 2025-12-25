"""
TanStack AI event stream transformer.

Transforms pydantic-ai native events into TanStack StreamChunk events.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    Generic,
    Literal,
    Mapping,
    Optional,
)

from pydantic_ai.messages import (
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.output import OutputDataT
from pydantic_ai.tools import AgentDepsT

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
from .request_types import RequestData

if TYPE_CHECKING:
    from pydantic_ai import (
        AgentRunResultEvent,
        FunctionToolCallEvent,
        FunctionToolResultEvent,
    )
    from pydantic_ai.messages import (
        FilePart,
        PartDeltaEvent,
        PartStartEvent,
        TextPart,
        TextPartDelta,
        ThinkingPart,
        ThinkingPartDelta,
    )


FinishReason = Literal["stop", "tool_calls", "length", "content_filter"] | None

logger = logging.getLogger(__name__)


def _normalize_finish_reason(
    reason: FinishReason | str | None,
) -> Literal["stop", "length", "tool_calls", "content_filter"]:
    """
    Normalize finish reason to the allowed TanStack/OpenAI-compatible values.

    Note: errors are emitted via ErrorStreamChunk; DoneStreamChunk.finishReason
    must remain within the allowed literal set.
    """
    if reason in ("stop", "length", "tool_calls", "content_filter"):
        return reason
    return "stop"


@dataclass
class TanStackEventStream(Generic[AgentDepsT, OutputDataT]):
    """
    UI event stream transformer for TanStack AI protocol.

    Transforms pydantic-ai native events into TanStack StreamChunk format,
    following the UIEventStream pattern from pydantic-ai.

    This class handles:
    - Text content streaming (ContentStreamChunk)
    - Thinking/reasoning streaming (ThinkingStreamChunk)
    - Tool call events (ToolCallStreamChunk)
    - Tool result events (ToolResultStreamChunk)
    - Deferred tool handling (ApprovalRequestedStreamChunk, ToolInputAvailableStreamChunk)
    - Stream lifecycle (DoneStreamChunk, ErrorStreamChunk)

    The `message_id` (used as chunk `id`) is derived from `run_input.run_id`.
    This allows clients to identify the run for continuation requests.
    """

    run_input: RequestData
    accept: Optional[str] = None
    # message_id is set in __post_init__ from run_input.run_id
    message_id: str = field(init=False)

    # Internal state
    _text_accumulator: Dict[int, str] = field(default_factory=dict)
    _thinking_accumulator: Dict[int, str] = field(default_factory=dict)
    _tool_call_index: int = 0
    _finish_reason: FinishReason = None
    _model_name: str = "unknown"

    def __post_init__(self) -> None:
        """Initialize message_id from run_input.run_id or generate new one."""
        self.message_id = self.run_input.run_id or uuid.uuid4().hex

    @property
    def response_headers(self) -> Mapping[str, str]:
        """Response headers for TanStack AI SSE stream."""
        return {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }

    def encode_event(self, event: StreamChunk) -> str:
        """Encode a StreamChunk as SSE data frame."""
        payload = json.dumps(event.model_dump(by_alias=True), ensure_ascii=False)
        return f"data: {payload}\n\n"

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle hooks
    # ─────────────────────────────────────────────────────────────────

    async def before_stream(self) -> AsyncIterator[StreamChunk]:
        """Called before streaming begins. Can emit initial chunks."""
        return
        yield  # Make this a generator

    async def after_stream(self) -> AsyncIterator[StreamChunk]:
        """Called after streaming completes. Emits done chunk."""
        yield DoneStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            finishReason=_normalize_finish_reason(self._finish_reason),
        )

    async def on_error(self, error: Exception) -> AsyncIterator[StreamChunk]:
        """Called when an error occurs during streaming."""
        logger.error(
            "TanStack stream error (run_id=%s model=%s): %s",
            self.message_id,
            self._model_name,
            str(error),
            exc_info=error,
        )
        # Emit error separately; keep finishReason valid for DoneStreamChunk.
        self._finish_reason = "stop"
        yield ErrorStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            error=ErrorObj(message=str(error)),
        )

    # ─────────────────────────────────────────────────────────────────
    # Text content handlers
    # ─────────────────────────────────────────────────────────────────

    async def handle_text_start(
        self, event: "PartStartEvent", part: "TextPart"
    ) -> AsyncIterator[StreamChunk]:
        """Handle start of text content."""
        self._text_accumulator[event.index] = part.content
        if part.content:
            yield ContentStreamChunk(
                id=self.message_id,
                model=self._model_name,
                timestamp=now_ms(),
                content=part.content,
                delta=part.content,
                role="assistant",
            )

    async def handle_text_delta(
        self, event: "PartDeltaEvent", delta: "TextPartDelta"
    ) -> AsyncIterator[StreamChunk]:
        """Handle text content delta."""
        delta_text = delta.content_delta
        idx = event.index
        prev = self._text_accumulator.get(idx, "")
        new_content = prev + delta_text
        self._text_accumulator[idx] = new_content
        yield ContentStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            content=new_content,
            delta=delta_text,
            role="assistant",
        )

    # ─────────────────────────────────────────────────────────────────
    # Thinking/reasoning handlers
    # ─────────────────────────────────────────────────────────────────

    async def handle_thinking_start(
        self, event: "PartStartEvent", part: "ThinkingPart"
    ) -> AsyncIterator[StreamChunk]:
        """Handle start of thinking content."""
        self._thinking_accumulator[event.index] = part.content
        if part.content:
            yield ThinkingStreamChunk(
                id=self.message_id,
                model=self._model_name,
                timestamp=now_ms(),
                content=part.content,
                delta=part.content,
            )

    async def handle_thinking_delta(
        self, event: "PartDeltaEvent", delta: "ThinkingPartDelta"
    ) -> AsyncIterator[StreamChunk]:
        """Handle thinking content delta."""
        if delta.content_delta:
            delta_text = delta.content_delta
            idx = event.index
            prev = self._thinking_accumulator.get(idx, "")
            new_content = prev + delta_text
            self._thinking_accumulator[idx] = new_content
            yield ThinkingStreamChunk(
                id=self.message_id,
                model=self._model_name,
                timestamp=now_ms(),
                content=new_content,
                delta=delta_text,
            )

    # ─────────────────────────────────────────────────────────────────
    # Tool call handlers
    # ─────────────────────────────────────────────────────────────────

    async def handle_tool_call(
        self, event: "FunctionToolCallEvent"
    ) -> AsyncIterator[StreamChunk]:
        """Handle function tool call event."""
        part: ToolCallPart = event.part
        logger.info(
            "Tool call (run_id=%s): %s id=%s",
            self.message_id,
            part.tool_name,
            part.tool_call_id,
        )
        yield ToolCallStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            index=self._tool_call_index,
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
        self._tool_call_index += 1

    async def handle_tool_result(
        self, event: "FunctionToolResultEvent"
    ) -> AsyncIterator[StreamChunk]:
        """Handle function tool result event."""
        if isinstance(event.result, ToolReturnPart):
            content = event.result.content
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            preview = content if len(content) <= 200 else (content[:200] + "…")
            logger.info(
                "Tool result (run_id=%s): id=%s preview=%r",
                self.message_id,
                event.result.tool_call_id,
                preview,
            )
            yield ToolResultStreamChunk(
                id=self.message_id,
                model=self._model_name,
                timestamp=now_ms(),
                toolCallId=event.result.tool_call_id,
                content=content,
            )

    # ─────────────────────────────────────────────────────────────────
    # Deferred tool handlers (HITL / client tools)
    # ─────────────────────────────────────────────────────────────────

    async def handle_deferred_approval(
        self,
        tool_call_id: str,
        tool_name: str,
        args: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Handle deferred tool requiring approval."""
        yield ApprovalRequestedStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            toolCallId=tool_call_id,
            toolName=tool_name,
            input=args,
            approval=ApprovalObj(id=uuid.uuid4().hex),
        )

    async def handle_deferred_input(
        self,
        tool_call_id: str,
        tool_name: str,
        args: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Handle deferred tool requiring client-side execution."""
        yield ToolInputAvailableStreamChunk(
            id=self.message_id,
            model=self._model_name,
            timestamp=now_ms(),
            toolCallId=tool_call_id,
            toolName=tool_name,
            input=args,
        )

    # ─────────────────────────────────────────────────────────────────
    # Result handlers
    # ─────────────────────────────────────────────────────────────────

    async def handle_run_result(
        self, event: "AgentRunResultEvent"
    ) -> AsyncIterator[StreamChunk]:
        """Handle agent run result event."""
        from pydantic_ai import DeferredToolRequests

        output = event.result.output
        if isinstance(output, DeferredToolRequests):
            self._finish_reason = "tool_calls"
            # Emit deferred chunks
            for part in output.approvals:
                async for chunk in self.handle_deferred_approval(
                    part.tool_call_id, part.tool_name, part.args
                ):
                    yield chunk
            for part in output.calls:
                async for chunk in self.handle_deferred_input(
                    part.tool_call_id, part.tool_name, part.args
                ):
                    yield chunk
        else:
            self._finish_reason = "stop"
        return
        yield  # Make this a generator

    # ─────────────────────────────────────────────────────────────────
    # Main transform method
    # ─────────────────────────────────────────────────────────────────

    async def transform_stream(
        self,
        native_events: AsyncIterator[Any],
        *,
        model_name: str = "unknown",
    ) -> AsyncIterator[StreamChunk]:
        """
        Transform pydantic-ai native events into TanStack StreamChunks.

        This is the main entry point for event transformation.
        """
        from pydantic_ai import (
            AgentRunResultEvent,
            FunctionToolCallEvent,
            FunctionToolResultEvent,
        )
        from pydantic_ai.messages import (
            PartDeltaEvent,
            PartStartEvent,
            TextPart,
            TextPartDelta,
            ThinkingPart,
            ThinkingPartDelta,
        )

        self._model_name = model_name

        # Lifecycle: before stream
        async for chunk in self.before_stream():
            yield chunk

        try:
            async for event in native_events:
                # Dispatch to appropriate handler based on event type
                if isinstance(event, PartStartEvent):
                    if isinstance(event.part, TextPart):
                        async for chunk in self.handle_text_start(event, event.part):
                            yield chunk
                    elif isinstance(event.part, ThinkingPart):
                        async for chunk in self.handle_thinking_start(
                            event, event.part
                        ):
                            yield chunk

                elif isinstance(event, PartDeltaEvent):
                    if isinstance(event.delta, TextPartDelta):
                        async for chunk in self.handle_text_delta(event, event.delta):
                            yield chunk
                    elif isinstance(event.delta, ThinkingPartDelta):
                        async for chunk in self.handle_thinking_delta(
                            event, event.delta
                        ):
                            yield chunk

                elif isinstance(event, FunctionToolCallEvent):
                    async for chunk in self.handle_tool_call(event):
                        yield chunk

                elif isinstance(event, FunctionToolResultEvent):
                    async for chunk in self.handle_tool_result(event):
                        yield chunk

                elif isinstance(event, AgentRunResultEvent):
                    async for chunk in self.handle_run_result(event):
                        yield chunk

        except Exception as exc:
            async for chunk in self.on_error(exc):
                yield chunk

        # Lifecycle: after stream
        async for chunk in self.after_stream():
            yield chunk
