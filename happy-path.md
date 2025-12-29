```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend (useChat/useChatSession)
  participant BE as Backend (FastAPI /api/chat)
  participant AD as TanStackAIAdapter (tanstack_pydantic_ai)
  participant AG as pydantic-ai Agent
  participant DB as Postgres
  participant AS as ArtifactStore (/api/data)

  U->>FE: Send message
  FE->>BE: POST /api/chat (messages + optional run_id)
  BE->>AD: from_request(...)
  AD->>AG: agent.run_stream_events(...)

  AG-->>AD: tool_call (e.g., preview_schema / execute_sql)
  AD-->>FE: StreamChunk(tool_call)

  alt Tool requires approval
    AD-->>FE: StreamChunk(approval-requested)
    FE->>BE: POST /api/chat (run_id + approvals{toolCallId:true/false})
    BE->>AD: continuation request
    AD->>AG: agent continues with DeferredToolResults
  end

  alt execute_sql approved
    AG->>DB: run SQL
    DB-->>AG: rows
    AG->>BE: store artifact
    AG-->>AD: tool_result
    AD-->>FE: StreamChunk(tool_result)
    FE->>AS: GET /api/data/{run_id}/{artifact_id}
    AS-->>FE: dataset preview
  end

  alt export_csv flow
    AG-->>AD: tool-input-available (client tool needed)
    AD-->>FE: StreamChunk(tool-input-available)
    FE->>FE: build CSV + trigger download
    FE->>BE: POST /api/chat (run_id + tool_results{toolCallId: {...}})
    BE->>AD: continuation request
    AD->>AG: agent continues with DeferredToolResults
  end

  AG-->>AD: done/content chunks
  AD-->>FE: StreamChunk(content/done)
```

This maps directly to TanStack AI’s [StreamChunkType](https://tanstack.com/ai/latest/docs/reference/type-aliases/StreamChunkType) protocol:
- `content`
- `tool_call`
- `tool_result`
- `done`
- `error`
- `approval-requested`
- `tool-input-available`
- `thinking` (unused)
