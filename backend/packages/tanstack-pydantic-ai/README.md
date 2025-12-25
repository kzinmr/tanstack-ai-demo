# tanstack-pydantic-ai

TanStack AI-compatible streaming backend for pydantic-ai.

## Features

- Two APIs for different use cases:
  - **Functional API**: `stream_chat()`, `stream_continue()` - framework-agnostic streaming
  - **UIAdapter API**: `TanStackAIAdapter` - class-based pattern following pydantic-ai's UIAdapter
- Full [TanStack AI StreamChunk](https://tanstack.com/ai/latest/docs/reference/type-aliases/StreamChunk) protocol support
- Stateful continuation for Human-in-the-Loop (HITL) flows
- Support for pydantic-ai [Deferred Tools](https://ai.pydantic.dev/deferred-tools/)

## Installation

```sh
uv add git+https://github.com/kzinmr/tanstack-pydantic-ai.git
```

## Module Structure

```
tanstack_pydantic_ai/
├── shared/        # Shared components (StreamChunk, SSE, Store)
├── functional/    # Function-based streaming API
├── adapter/       # UIAdapter-based API
└── ui/tanstack/   # Alias for adapter (backward compatibility)
```

## Quick Start

### Option 1: UIAdapter API (Recommended)

The UIAdapter pattern provides a clean, class-based interface:

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic_ai import Agent

from tanstack_pydantic_ai import TanStackAIAdapter, InMemoryRunStore

agent = Agent("openai:gpt-4o-mini")
store = InMemoryRunStore()  # For stateful continuation

app = FastAPI()

@app.post("/api/chat")
async def chat(request: Request):
    adapter = TanStackAIAdapter.from_request(
        agent=agent,
        body=await request.body(),
        store=store,
    )
    return StreamingResponse(
        adapter.streaming_response(),
        headers=dict(adapter.response_headers),
    )

@app.post("/api/chat/continue")
async def chat_continue(request: Request):
    adapter = TanStackAIAdapter.from_request(
        agent=agent,
        body=await request.body(),
        store=store,
    )
    return StreamingResponse(
        adapter.streaming_response(),
        headers=dict(adapter.response_headers),
    )
```

### Option 2: Functional API

For more control or custom frameworks:

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic_ai import Agent

from tanstack_pydantic_ai import (
    stream_chat,
    InMemoryRunStore,
    dump_chunk,
    sse_data,
    encode_done,
)

agent = Agent("openai:gpt-4o-mini")
store = InMemoryRunStore()

app = FastAPI()

@app.post("/chat")
async def chat(messages: list, model: str = None):
    user_prompt = messages[-1]["content"]

    async def generate():
        stream = stream_chat(agent, user_prompt, model=model)

        async for chunk in stream:
            yield sse_data(dump_chunk(chunk))

        # Save result for continuation
        result = await stream.result()
        store.set_messages(stream.run_id, result.all_messages(), model)

        yield encode_done()

    return StreamingResponse(generate(), media_type="text/event-stream")
```

## API Reference

### Functional API

```python
from tanstack_pydantic_ai.functional import stream_chat, stream_continue, StreamResult

# Start a new chat
stream: StreamResult = stream_chat(
    agent,
    user_prompt="Hello!",
    message_history=None,  # Optional
    model=None,            # Optional model override
    run_id=None,           # Optional (auto-generated)
)

# Iterate over chunks
async for chunk in stream:
    print(chunk.type)  # content, thinking, tool_call, tool_result, done, error

# Get final result
result = await stream.result()
messages = result.all_messages()
output = result.output  # str | DeferredToolRequests
```

### UIAdapter API

```python
from tanstack_pydantic_ai.ui.tanstack import TanStackAIAdapter, TanStackEventStream
# Or: from tanstack_pydantic_ai.adapter import TanStackAIAdapter

adapter = TanStackAIAdapter.from_request(
    agent=agent,
    body=request_body,
    accept=None,           # Optional Accept header
    deps=None,             # Optional agent dependencies
    store=None,            # Optional store for stateful continuation
)

# Properties
adapter.run_id              # Unique run ID for continuation
adapter.is_continuation     # True if this is a continuation request
adapter.message_history     # Loaded from store or request
adapter.user_prompt         # Extracted user prompt

# Streaming
async for chunk in adapter.run_stream():
    ...  # StreamChunk objects

# Full SSE response
async for data in adapter.streaming_response():
    ...  # bytes (SSE-encoded)
```

### Shared Components

```python
from tanstack_pydantic_ai.shared import (
    # Chunk types
    StreamChunk,
    ContentStreamChunk,
    ThinkingStreamChunk,
    ToolCallStreamChunk,
    ToolResultStreamChunk,
    ApprovalRequestedStreamChunk,
    DoneStreamChunk,
    ErrorStreamChunk,

    # Store
    InMemoryRunStore,
    RunState,

    # SSE utilities
    encode_chunk,
    encode_done,
    dump_chunk,
    sse_data,
    now_ms,
)
```

## StreamChunk Types

| Type | Description |
|------|-------------|
| `content` | Text content with delta streaming |
| `thinking` | Reasoning/thinking content (Claude extended thinking) |
| `tool_call` | Function tool invocation |
| `tool_result` | Tool execution result |
| `tool-input-available` | Deferred tool ready for client execution |
| `approval-requested` | Tool requires user approval |
| `error` | Error occurred |
| `done` | Stream completed |

## Stateful Continuation (HITL)

For Human-in-the-Loop flows with deferred tools:

1. **Initial request** → Server saves message history with `run_id`
2. **Response chunks** include `id` field (= `run_id`)
3. **Continuation request** sends `run_id` + `tool_results`/`approvals`
4. **Server loads history** from store and continues

```python
# Continuation request format
{
    "run_id": "abc123",
    "tool_results": {"tool_call_id_1": "result value"},
    "approvals": {"tool_call_id_2": true},
    "messages": []  # Ignored in stateful mode
}
```

## Demo

```sh
# Start demo server
uv run uvicorn examples.backend.demo_server:app --host 127.0.0.1 --port 8000 &

# Run frontend verification
cd examples/frontend
npm run verify
```

## References

- [TanStack AI StreamChunk](https://tanstack.com/ai/latest/docs/reference/type-aliases/StreamChunk)
- [pydantic-ai Deferred Tools](https://ai.pydantic.dev/deferred-tools/)
- [pydantic-ai UIAdapter](https://ai.pydantic.dev/ui/)
