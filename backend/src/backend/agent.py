"""
Agent definition for the SQL analysis agent.

Based on pydantic-ai sql-gen example with HITL support.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    ModelRetry,
    RunContext,
    format_as_xml,
)

from .db import DB_SCHEMA, SQL_EXAMPLES
from .deps import Deps
from .settings import get_settings
from .tools import register_tools

# Get settings
settings = get_settings()


@lru_cache
def get_agent() -> Agent[Deps, str | DeferredToolRequests]:
    """
    Lazily create the Agent.

    This avoids crashing the FastAPI app import if the LLM provider is not
    configured yet (e.g. missing API keys). Errors are handled at request time.
    """
    agent: Agent[Deps, str | DeferredToolRequests] = Agent(
        settings.llm_model,
        deps_type=Deps,
        output_type=[str, DeferredToolRequests],
    )
    register_tools(agent)
    # Register prompt/validators lazily as well (avoid module import-time failures)
    agent.system_prompt(system_prompt)
    agent.output_validator(validate_sql_output)
    return agent


async def system_prompt() -> str:
    """Generate the system prompt with current date and schema."""
    return f"""\
You are a helpful data analyst assistant. Your job is to help users analyze
log data stored in a PostgreSQL database.

## Database Schema

{DB_SCHEMA}

## Today's Date

{date.today()}

## Important Rules

1. **Safety First**: Only SELECT queries are allowed. Never modify data.
2. **Always Use LIMIT**: Every query must include LIMIT to prevent large result sets.
3. **Ask for Approval**: The execute_sql tool requires user approval before running.
   This is for safety - always explain what the query will do before it runs.
4. **Use Artifact IDs**: After executing SQL, results are stored with an artifact_id.
   Use the display tool to show data, and run_duckdb for further analysis.
   In run_duckdb queries, refer to the table as `dataset`.
   Do not show artifact_id to the user directly.
   Tool results include a JSON payload with artifacts[].id for internal use.
5. **CSV Export**: When the user wants to download data as CSV, use export_csv.
   This also requires approval and runs on the client side.

## Workflow Example

1. User asks to analyze error logs from yesterday
2. You write a SQL query and call execute_sql (requires approval)
3. After approval, the query runs and results are stored as an artifact_id
4. Use display to show a preview of the data (do not mention artifact_id to the user)
5. If user wants to download, use export_csv (requires approval + client execution)

## SQL Examples

{format_as_xml(SQL_EXAMPLES)}
"""


async def validate_sql_output(ctx: RunContext[Deps], output: Any) -> Any:
    """
    Validate that SQL queries are safe.

    This validator checks generated SQL queries (from structured output)
    to ensure they are SELECT-only and include LIMIT.
    """
    # If it's a DeferredToolRequests, let it pass through
    if isinstance(output, DeferredToolRequests):
        return output

    # For string output, just return it
    if isinstance(output, str):
        return output

    # If we have a structured output with sql_query field, validate it
    if hasattr(output, "sql_query"):
        sql = output.sql_query.strip().upper()

        # Remove backslashes (common Gemini issue)
        output.sql_query = output.sql_query.replace("\\", "")

        # Check SELECT only
        if not sql.startswith("SELECT"):
            raise ModelRetry(
                "Only SELECT queries are allowed. Please rewrite the query."
            )

        # Check for LIMIT (relaxed check - some queries like COUNT don't need it)
        if "LIMIT" not in sql and "COUNT" not in sql and "SUM" not in sql:
            raise ModelRetry(
                "Please add a LIMIT clause to prevent returning too many rows. "
                "For example: LIMIT 100"
            )

    return output
