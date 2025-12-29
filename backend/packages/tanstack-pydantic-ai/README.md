# tanstack-pydantic-ai

TanStack AI-compatible streaming backend for pydantic-ai.

## Features

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
├── adapter/       # UIAdapter-based API (TanStackAIAdapter, TanStackEventStream)
└── shared/        # Shared components (StreamChunk types, SSE utilities, Store)
```

## Quick Start

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic_ai import Agent

from tanstack_pydantic_ai import TanStackAIAdapter, InMemoryRunStore

agent = Agent("openai:gpt-5-mini")
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
```

Continuation requests can be sent to the same endpoint with `run_id` and
`tool_results`/`approvals` in the request body.

## API Reference

### UIAdapter API

```python
from tanstack_pydantic_ai import TanStackAIAdapter, TanStackEventStream

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

# Optional error handling helpers
async for data in TanStackAIAdapter.stream_with_error_handling(
    adapter.streaming_response(),
    model="unknown",
    run_id=adapter.run_id,
):
    ...  # bytes (SSE-encoded)
```

### Public Exports

```python
from tanstack_pydantic_ai import (
    # Store
    InMemoryRunStore,
    RunState,
    # Stream chunk typing
    StreamChunk,
    StreamChunkType,
)
```

Low-level chunk models, request types, and SSE helpers are internal and may change; import them from submodules if you need them (`tanstack_pydantic_ai.shared.*`, `tanstack_pydantic_ai.adapter.request_types`).

## StreamChunk Types

| Type                   | Description                              |
| ---------------------- | ---------------------------------------- |
| `content`              | Text content with delta streaming        |
| `done`                 | Stream completed                         |
| `error`                | Error occurred                           |
| `tool_call`            | Function tool invocation                 |
| `tool_result`          | Tool execution result                    |
| `tool-input-available` | Deferred tool ready for client execution |
| `approval-requested`   | Tool requires user approval              |
| `thinking`             | Reasoning/thinking content               |

## Stateful Continuation (HITL)

For Human-in-the-Loop flows with deferred tools:

1. **Initial request** → Server saves message history with `run_id`
2. **Response chunks** include `id` field (= `run_id`)
3. **Continuation request** sends `run_id` + `tool_results`/`approvals`
4. **Server loads history** from store and continues

Note: this adapter emits `approval.id` as the tool call ID so client approvals
can be keyed by `tool_call_id` without extra mapping.

```python
# Continuation request format
{
    "run_id": "abc123",
    "tool_results": {"tool_call_id_1": "result value"},
    "approvals": {"tool_call_id_2": true},
    "messages": []  # Ignored in stateful mode
}
```

## Testing

```sh
cd backend
uv run pytest packages/tanstack-pydantic-ai/tests
```

## References

- [TanStack AI StreamChunk](https://tanstack.com/ai/latest/docs/reference/type-aliases/StreamChunk)
- [pydantic-ai UIAdapter](https://ai.pydantic.dev/ui/)
- [pydantic-ai Deferred Tools](https://ai.pydantic.dev/deferred-tools/)
