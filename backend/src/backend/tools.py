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

import re

import duckdb
import pandas as pd
from pydantic_ai import CallDeferred, RunContext

from .data_store import csv_data_store
from .db import DB_SCHEMA
from .deps import Deps
from .settings import get_settings

if TYPE_CHECKING:
    from pydantic_ai import Agent


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
            A message indicating success with the result reference (e.g., "Out[1]")
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
            ref = ctx.deps.store(df)
            # Make the dataset resolvable by the frontend via /api/data/{dataset}.
            # This enables preview/export even when the assistant only mentions Out[n].
            original_row_count = len(df)
            max_rows = settings.sql_max_limit
            df_serializable = df.copy()
            for col in df_serializable.columns:
                if pd.api.types.is_datetime64_any_dtype(df_serializable[col]):
                    df_serializable[col] = df_serializable[col].astype(str)
            limited_df = df_serializable.head(max_rows)
            csv_data_store().store(
                dataset_ref=ref,
                rows=limited_df.to_dict(orient="records"),
                columns=list(limited_df.columns),
                original_row_count=original_row_count,
            )

            # Return a short, accurate summary + preview (first 5 rows).
            preview_rows = min(5, original_row_count)
            preview = df.head(preview_rows).to_string()
            return (
                f"クエリを実行し、結果を `{ref}` として保存しました。"
                f"取得した行数（クエリ結果）: {original_row_count}。\n\n"
                f"プレビュー（先頭 {preview_rows} 行）:\n{preview}"
            )
        except Exception as e:
            return f"SQLの実行に失敗しました: {e}"

    @agent.tool
    async def display(ctx: RunContext[Deps], dataset: str, rows: int = 5) -> str:
        """
        Display the first N rows of a stored dataset.

        Args:
            dataset: Reference to the dataset (e.g., "Out[1]")
            rows: Number of rows to display (default: 5, max: 20)

        Returns:
            A string representation of the DataFrame head
        """
        rows = min(rows, 20)  # Cap at 20 rows
        df = ctx.deps.get(dataset)
        # Ensure the dataset reference is resolvable via /api/data/{dataset} for
        # later CSV export flows, even when the original dataset was produced in
        # a previous request/run.
        try:
            original_row_count = len(df)
            max_rows = settings.sql_max_limit
            df_serializable = df.copy()
            for col in df_serializable.columns:
                if pd.api.types.is_datetime64_any_dtype(df_serializable[col]):
                    df_serializable[col] = df_serializable[col].astype(str)
            limited_df = df_serializable.head(max_rows)
            csv_data_store().store(
                dataset_ref=dataset,
                rows=limited_df.to_dict(orient="records"),
                columns=list(limited_df.columns),
                original_row_count=original_row_count,
            )
        except Exception:
            # Best-effort: display should still work even if caching fails.
            pass
        return (
            f"Contents of {dataset} (first {rows} rows):\n{df.head(rows).to_string()}"
        )

    @agent.tool
    async def run_duckdb(ctx: RunContext[Deps], dataset: str, sql: str) -> str:
        """
        Run a DuckDB SQL query on a stored DataFrame.

        Use this for data analysis operations like aggregations, filtering, etc.
        The virtual table name in the SQL must be 'dataset'.

        Args:
            dataset: Reference to the source DataFrame (e.g., "Out[1]")
            sql: DuckDB SQL query. Use 'dataset' as the table name.

        Returns:
            A message indicating success with the result reference
        """
        df = ctx.deps.get(dataset)
        try:
            result = duckdb.query_df(df=df, virtual_table_name="dataset", sql_query=sql)
            result_df = result.df()
            ref = ctx.deps.store(result_df)
            # Also store for /api/data/{dataset} so the frontend can preview/export.
            original_row_count = len(result_df)
            max_rows = settings.sql_max_limit
            df_serializable = result_df.copy()
            for col in df_serializable.columns:
                if pd.api.types.is_datetime64_any_dtype(df_serializable[col]):
                    df_serializable[col] = df_serializable[col].astype(str)
            limited_df = df_serializable.head(max_rows)
            csv_data_store().store(
                dataset_ref=ref,
                rows=limited_df.to_dict(orient="records"),
                columns=list(limited_df.columns),
                original_row_count=original_row_count,
            )
            return f"DuckDB query executed. Result stored as `{ref}` ({len(result_df)} rows)"
        except Exception as e:
            return f"Error executing DuckDB query: {e}"

    # NOTE: export_csv is a client-side tool (CallDeferred). We mark it as
    # requires_approval so the demo shows HITL before the client execution.
    @agent.tool(requires_approval=True)
    async def export_csv(ctx: RunContext[Deps], dataset: str) -> str:
        """
        Export a dataset as CSV file (executed on client side).

        This tool is executed in the browser (client-side).
        The client will receive the data reference and fetch the actual data
        from /api/data/{dataset} endpoint.

        Args:
            dataset: Reference to the dataset to export (e.g., "Out[1]")

        Returns:
            Never returns normally - raises CallDeferred for client execution
        """
        # IMPORTANT:
        # `Deps.output` is per-request and is NOT persisted across /api/chat calls.
        # Therefore, exporting by dataset reference (e.g. Out[1]) must not rely on
        # ctx.deps.get(dataset) here.
        #
        # Instead, we rely on the server-side csv_data_store keyed by dataset ref,
        # which is populated when datasets are created (execute_sql/run_duckdb).
        # The client tool panel will fetch the actual data from /api/data/{dataset}.
        if csv_data_store().get(dataset) is None:
            return (
                f"エクスポート対象のデータ `{dataset}` が見つかりませんでした。"
                "直前にクエリを実行して結果（Out[n]）を作成してから、もう一度CSV出力してください。"
            )

        # Raise CallDeferred - the dataset reference is included in the tool args,
        # which get forwarded to tool-input-available.input (e.g. {dataset: "Out[1]"}).
        raise CallDeferred()
