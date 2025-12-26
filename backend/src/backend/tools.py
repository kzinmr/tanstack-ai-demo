"""
Tool definitions for the SQL analysis agent.

This module defines tools that the agent can use, including:
- preview_schema: Show database schema (no approval needed)
- execute_sql: Execute SQL query (HITL - approval required)
- display: Show DataFrame contents (no approval needed)
- run_duckdb: Run DuckDB SQL on DataFrame (no approval needed)
- export_csv: Export to CSV (HITL - client-side execution)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import json
import re

import duckdb
import pandas as pd
from pydantic_ai import CallDeferred, ModelRetry, RunContext

from .db import DB_SCHEMA
from .deps import Deps
from .settings import get_settings

if TYPE_CHECKING:
    from pydantic_ai import Agent


def _tool_result(
    message: str, artifacts: list[dict[str, object]] | None = None
) -> str:
    payload: dict[str, object] = {"message": message}
    if artifacts:
        payload["artifacts"] = artifacts
    return json.dumps(payload, ensure_ascii=False)


def register_tools(agent: "Agent[Deps, ...]") -> None:
    """Register all tools with the agent."""

    settings = get_settings()

    @agent.tool
    async def preview_schema(ctx: RunContext[Deps]) -> str:
        """
        Show the database schema for the records table.

        Use this to understand the structure before writing SQL queries.
        """
        return f"Database Schema:\n{DB_SCHEMA}"

    @agent.tool(requires_approval=True)
    async def execute_sql(ctx: RunContext[Deps], sql: str) -> str:
        """
        Execute a SQL query on the database after user approval.

        This tool requires user approval before execution because SQL queries
        can potentially access sensitive data or cause performance issues.

        Args:
            sql: The SQL query to execute. Only SELECT queries are allowed.
                 Always include LIMIT to prevent large result sets.

        Returns:
            A message indicating success with the artifact_id
        """
        # Validate SQL is SELECT only
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return "Error: Only SELECT queries are allowed for safety."

        # Enforce LIMIT for safety - add if not present
        max_limit = settings.sql_max_limit
        if "LIMIT" not in sql_upper:
            sql = f"{sql.rstrip().rstrip(';')} LIMIT {max_limit}"
        else:
            # Check if existing LIMIT is too high
            limit_match = re.search(r"LIMIT\s+(\d+)", sql_upper)
            if limit_match:
                existing_limit = int(limit_match.group(1))
                if existing_limit > max_limit:
                    # Replace with max_limit
                    sql = re.sub(
                        r"LIMIT\s+\d+",
                        f"LIMIT {max_limit}",
                        sql,
                        flags=re.IGNORECASE,
                    )

        try:
            rows = await ctx.deps.conn.fetch(sql)
            df = pd.DataFrame([dict(r) for r in rows])
            artifact = ctx.deps.artifact_store.store(ctx.deps.run_id, df)

            # Return a short, accurate summary + preview (first 5 rows).
            row_count = len(df)
            preview_rows = min(5, row_count)
            preview = df.head(preview_rows).to_string()
            return _tool_result(
                message=(
                    f"クエリを実行しました（{row_count}行）。\n\n"
                    f"プレビュー（先頭 {preview_rows} 行）:\n{preview}"
                ),
                artifacts=[
                    {
                        "id": artifact.id,
                        "type": artifact.type,
                        "row_count": row_count,
                    }
                ],
            )
        except Exception as e:
            return f"SQLの実行に失敗しました: {e}"

    @agent.tool
    async def display(
        ctx: RunContext[Deps], artifact_id: str, rows: int = 5
    ) -> str:
        """
        Display the first N rows of a stored dataset.

        Args:
            artifact_id: Artifact ID to display
            rows: Number of rows to display (default: 5, max: 20)

        Returns:
            A string representation of the DataFrame head
        """
        rows = min(rows, 20)  # Cap at 20 rows
        df = ctx.deps.artifact_store.get_dataframe(ctx.deps.run_id, artifact_id)
        if df is None:
            raise ModelRetry(
                f"Error: {artifact_id} is not a valid artifact reference."
            )
        return f"Contents (first {rows} rows):\n{df.head(rows).to_string()}"

    @agent.tool
    async def run_duckdb(
        ctx: RunContext[Deps], artifact_id: str, sql: str
    ) -> str:
        """
        Run a DuckDB SQL query on a stored DataFrame.

        Use this for data analysis operations like aggregations, filtering, etc.
        The virtual table name in the SQL must be 'dataset'.

        Args:
            artifact_id: Reference to the source artifact
            sql: DuckDB SQL query. Use 'dataset' as the table name.

        Returns:
            A message indicating success with the result reference
        """
        df = ctx.deps.artifact_store.get_dataframe(ctx.deps.run_id, artifact_id)
        if df is None:
            raise ModelRetry(
                f"Error: {artifact_id} is not a valid artifact reference."
            )
        try:
            result = duckdb.query_df(df=df, virtual_table_name="dataset", sql_query=sql)
            result_df = result.df()
            artifact = ctx.deps.artifact_store.store(ctx.deps.run_id, result_df)
            row_count = len(result_df)
            preview_rows = min(5, row_count)
            preview = result_df.head(preview_rows).to_string()
            return _tool_result(
                message=(
                    f"DuckDB query executed ({row_count} rows).\n\n"
                    f"Preview (first {preview_rows} rows):\n{preview}"
                ),
                artifacts=[
                    {
                        "id": artifact.id,
                        "type": artifact.type,
                        "row_count": row_count,
                    }
                ],
            )
        except Exception as e:
            return f"Error executing DuckDB query: {e}"

    # NOTE: export_csv is a client-side tool (CallDeferred). We mark it as
    # requires_approval so the demo shows HITL before the client execution.
    @agent.tool(requires_approval=True)
    async def export_csv(ctx: RunContext[Deps], artifact_id: str) -> str:
        """
        Export a dataset as CSV file (executed on client side).

        This tool is executed in the browser (client-side).
        The client will receive the data reference and fetch the actual data
        from /api/data/{artifact_id} endpoint.

        Args:
            artifact_id: Reference to the artifact to export

        Returns:
            Never returns normally - raises CallDeferred for client execution
        """
        if ctx.deps.artifact_store.get(ctx.deps.run_id, artifact_id) is None:
            return (
                "エクスポート対象のデータが見つかりませんでした。"
                "直前にクエリを実行して結果を作成してから、もう一度CSV出力してください。"
            )

        # Raise CallDeferred - the artifact_id is included in the tool args.
        raise CallDeferred()
