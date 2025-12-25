# TanStack AI HITL Demo

A Human-in-the-Loop (HITL) chat demo using **TanStack AI + pydantic-ai**.

This demo showcases a SQL analysis agent that requires user approval before executing queries and exports results as CSV on the client side.

## Features

- **HITL (Human-in-the-Loop)**: Dangerous operations (SQL execution) require user approval
- **Client-side Tool Execution**: CSV export runs in the browser
- **SSE Streaming**: TanStack AI compatible real-time responses
- **Continuation**: Agent resumes processing after approval

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

## Demo Scenario

1. User requests: "Aggregate yesterday's error logs and download as CSV"
2. Agent generates SQL and calls `execute_sql` tool
3. **Approval modal** appears, user reviews SQL and clicks Approve
4. SQL executes, results stored as `Out[1]`
5. Agent calls `export_csv` tool
6. **Approval modal** → Approve → **CSV download panel** appears
7. User clicks "Download CSV" → browser downloads CSV file
8. Agent displays completion message

## Setup

### Prerequisites

- Python 3.11+
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
uv run uvicorn src.main:app --reload --port 8000
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

### API Endpoints

| Endpoint                  | Description                               |
| ------------------------- | ----------------------------------------- |
| `POST /api/chat`          | Start new chat stream                     |
| `POST /api/chat/continue` | HITL continuation (approval/tool results) |
| `GET /health`             | Health check                              |

### Request Examples

**New chat:**

```json
{
  "messages": [{ "role": "user", "content": "Show me yesterday's error logs" }]
}
```

**Send approval:**

```json
{
  "run_id": "abc123...",
  "approvals": { "tool_call_id_1": true }
}
```

**Send client tool result:**

```json
{
  "run_id": "abc123...",
  "tool_results": {
    "tool_call_id_2": { "filename": "result.csv", "rowCount": 100 }
  }
}
```

## Tools

| Tool             | Execution  | Approval | Description                    |
| ---------------- | ---------- | -------- | ------------------------------ |
| `preview_schema` | Server     | No       | Display DB schema              |
| `execute_sql`    | Server     | **Yes**  | Execute SQL query              |
| `display`        | Server     | No       | Show data preview              |
| `run_duckdb`     | Server     | No       | Run analytics SQL on DataFrame |
| `export_csv`     | **Client** | **Yes**  | Download CSV file              |

## Project Structure

```
tanstack-ai-demo/
├── backend/
│   ├── pyproject.toml      # Python dependencies
│   ├── .env.example        # Environment template
│   └── src/
│       ├── main.py         # FastAPI app
│       ├── agent.py        # pydantic-ai Agent definition
│       ├── tools.py        # Tool definitions (HITL enabled)
│       ├── deps.py         # RunContext dependencies
│       └── db.py           # DB connection & schema
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        └── features/chat/
            ├── ChatPage.tsx       # Main chat UI
            ├── useChatStream.ts   # Stream processing hook
            ├── sse.ts             # SSE parser
            ├── ApprovalModal.tsx  # Approval modal
            └── ToolInputPanel.tsx # CSV export UI

```

## Tech Stack

- [tanstack-pydantic-ai](https://github.com/kzinmr/tanstack-pydantic-ai) - TanStack AI compatible adapter

### Backend

- [pydantic-ai](https://ai.pydantic.dev/) - AI agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [asyncpg](https://github.com/MagicStack/asyncpg) - PostgreSQL driver
- [DuckDB](https://duckdb.org/) - Data analytics

### Frontend

- [TanStack AI](https://tanstack.com/ai) - AI streaming
- [React](https://react.dev/) + [Vite](https://vite.dev/)
- [BaseUI](https://baseweb.design/) - UI components
- [TailwindCSS](https://tailwindcss.com/) - Styling

## Related Documentation

- [pydantic-ai Deferred Tools](https://ai.pydantic.dev/deferred-tools/)
- [TanStack AI Docs](https://tanstack.com/ai/latest/docs)

## License

MIT
