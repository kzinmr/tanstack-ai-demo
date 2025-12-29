# TanStack AI HITL Demo

A Human-in-the-Loop (HITL) chat demo using **TanStack AI + pydantic-ai**.

This demo showcases a SQL analysis agent that requires user approval before executing queries and exports results as CSV on the client side.

## Features

- **HITL (Human-in-the-Loop)**: Dangerous operations (SQL execution) require user approval
- **Client-side Tool Execution**: CSV export runs in the browser
- **SSE Streaming**: TanStack AI compatible real-time responses
- **Continuation**: Agent resumes processing after approval
- **Dynamic Schema Preview**: `preview_schema` introspects the current database schema

## Architecture

```
┌─────────────────┐     SSE Stream      ┌─────────────────┐
│    Frontend     │ ◄─────────────────► │    Backend      │
│  React + Vite   │                     │    FastAPI      │
│  TanStack AI    │                     │   pydantic-ai   │
│  BaseUI         │                     │  tanstack-      │
│                 │                     │  pydantic-ai    │
└─────────────────┘                     └────────┬────────┘
                                                 │
                                                 ▼
                                        ┌─────────────────┐
                                        │   PostgreSQL    │
                                        │  (log records)  │
                                        └─────────────────┘
```

See [flow-overview.md](./flow-overview.md) in detail.

## Demo Scenario

1. User requests: "Aggregate yesterday's error logs and download as CSV"
2. Agent generates SQL and calls `execute_sql` tool (as [Server Tools](https://tanstack.com/ai/latest/docs/guides/server-tools))
3. Approval card appears inline, user reviews SQL and clicks Approve
4. SQL executes, results stored as an artifact and the UI shows a preview
5. Agent calls `export_csv` tool (as [Client Tools](https://tanstack.com/ai/latest/docs/guides/client-tools))
6. Approval card → Approve → CSV download panel appears
7. User clicks "Download CSV" → browser downloads CSV file
8. Agent displays completion message

See [happy-path.md](./happy-path.md) in detail.

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker (for PostgreSQL)
- uv (Python package manager)

### 1. Start PostgreSQL

```bash
docker run --rm -e POSTGRES_PASSWORD=postgres -p 54320:5432 postgres
```

### 2. Backend Setup

```bash
cd backend

# Configure environment variables
cp .env.example .env
# Edit .env and set your API key:
# - OPENAI_API_KEY=your-key (for OpenAI)
# - GEMINI_API_KEY=your-key (for Gemini)

# Install dependencies
uv sync

# Start server
uv run uvicorn src.backend.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

### 4. Open Browser

Navigate to http://localhost:5173

## Usage

### Example Input

Enter this message to experience the HITL flow:

> I want to aggregate yesterday's errors from `records`. You can write the SQL, but let me confirm before executing. I want to download the results as CSV, but confirm that too.

### Manual E2E Smoke Test

With the backend running (and an LLM provider configured), you can run a quick
HITL smoke script:

```bash
python scripts/e2e_hilt_smoke.py --base-url http://localhost:8000
```

### API Endpoints

| Endpoint                               | Description                              |
| -------------------------------------- | ---------------------------------------- |
| `POST /api/chat`                       | Start/continue chat stream (HITL)        |
| `GET /api/data/{run_id}/{artifact_id}` | Get artifact data by run and artifact ID (preview) |
| `GET /health`                          | Health check                             |

### Request Examples

**New chat:**

```json
{
  "messages": [{ "role": "user", "content": "Show me yesterday's error logs" }]
}
```

**Send approval (same endpoint):**

```json
{
  "run_id": "abc123...",
  "approvals": { "tool_call_id_1": true }
}
```

**Send client tool result (same endpoint):**

```json
{
  "run_id": "abc123...",
  "tool_results": {
    "tool_call_id_2": { "filename": "result.csv", "rowCount": 100 }
  }
}
```

### Storage Backends (Ports)

The backend uses ports for run state and artifact storage so you can swap in
shared stores in production.

Defaults:

- `RUN_STORE_BACKEND=memory`
- `ARTIFACT_STORE_BACKEND=memory`

S3 artifact store (signed URL downloads):

- `ARTIFACT_STORE_BACKEND=s3`
- `S3_BUCKET=...`
- `S3_PREFIX=tanstack-ai-demo`
- `S3_REGION=...`
- `S3_SIGNED_URL_EXPIRES_IN=900`
- Requires `boto3` installed in the backend environment.

When `mode=download` is passed to `/api/data/{run_id}/{artifact_id}`, the backend
returns a signed URL instead of inline rows if the artifact store supports it.

## Tools

| Tool             | Execution  | Approval | Description            |
| ---------------- | ---------- | -------- | ---------------------- |
| `preview_schema` | Server     | No       | Preview live DB schema |
| `execute_sql`    | Server     | **Yes**  | Execute SQL query      |
| `export_csv`     | **Client** | **Yes**  | Download CSV file      |

### Tool Result Envelope

Tool results are returned as JSON strings with a versioned envelope. The UI
parses this shape to extract `message` and `artifacts`; anything else is treated
as a raw tool result.

```json
{
  "type": "tool_result",
  "version": 1,
  "message": "Query executed.",
  "artifacts": [{ "id": "a_abc123_1", "type": "table", "row_count": 10 }],
  "data": { "success": true }
}
```

## Project Structure

```
tanstack-ai-demo/
├── backend/
│   ├── pyproject.toml           # Python dependencies
│   ├── .env.example             # Environment template
│   ├── packages/
│   │   └── tanstack-pydantic-ai/  # TanStack AI adapter library
│   └── src/backend/
│       ├── main.py              # FastAPI app
│       ├── agent.py             # pydantic-ai Agent definition
│       ├── settings.py          # Application settings
│       ├── deps.py              # RunContext dependencies
│       ├── db.py                # DB connection & schema
│       ├── store/               # Artifact store
│       └── tools/               # Tool definitions (HITL enabled)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        └── features/chat/
            ├── ChatPage.tsx       # Main chat UI
            ├── chatConnection.ts  # TanStack AI connection adapter
            ├── components/        # UI components
            ├── hooks/             # Custom hooks (TanStack AI useChat wrapper)
            ├── services/          # API services
            ├── types/             # TypeScript types
            └── utils/             # Utility functions
```

## Tech Stack

### Frontend

- [TanStack AI](https://tanstack.com/ai) - AI streaming
- [React](https://react.dev/) + [Vite](https://vite.dev/)
- [BaseUI](https://baseweb.design/) - UI components
- [TailwindCSS](https://tailwindcss.com/) - Styling

### Backend

- [Pydantic AI](https://ai.pydantic.dev/) - AI agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [asyncpg](https://github.com/MagicStack/asyncpg) - PostgreSQL driver

### UI Adapter for Agents

- [tanstack-pydantic-ai](https://github.com/kzinmr/tanstack-pydantic-ai) - TanStack AI compatible adapter

This package is the “protocol glue”:

- It parses incoming TanStack AI-style requests (messages + optional `run_id`, approvals, tool_results).
- It calls [pydantic-ai’s event streaming APIs](https://ai.pydantic.dev/agents/#streaming-all-events).
- It converts pydantic-ai events into TanStack AI [StreamChunks](https://tanstack.com/ai/latest/docs/reference/type-aliases/StreamChunk), and emits SSE frames.
- It stores per-run state so a run can pause (approval / client tool) and resume (via [Deferred Tools](https://ai.pydantic.dev/deferred-tools/); deferring tool execution and resuming with tool results).

This general approach matches pydantic-ai’s UI integration concepts: you can create an adapter layer responsible for turning agent runs into UI-facing events and handling re-entrancy/continuations. ([pydantic_ai.ui](https://ai.pydantic.dev/api/ui/base/))

**Important internal separation to preserve:**

- **Protocol transformation** (pydantic-ai events → TanStack StreamChunks) should remain in the adapter layer.
- **Business logic** (SQL safety, export behavior, artifact shaping) should remain in backend app `code/tools`.

## Related Documentation

- [TanStack AI Docs](https://tanstack.com/ai/latest/docs)
- [Pydantic AI Agents](https://ai.pydantic.dev/agents/)

Related agent examples:

- [sql-gen](https://ai.pydantic.dev/examples/sql-gen/): clear schema grounding, safe query patterns
- [data-analyst](https://ai.pydantic.dev/examples/data-analyst/): artifact-like workflows over datasets (passed via [dependencies](https://ai.pydantic.dev/dependencies/))

## License

MIT
