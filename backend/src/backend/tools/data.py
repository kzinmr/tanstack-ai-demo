from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb
from pydantic_ai import ModelRetry, RunContext

from ..deps import Deps
from ._common import _tool_result

if TYPE_CHECKING:
    from pydantic_ai import Agent


def register_data_tools(agent: "Agent[Deps, ...]") -> None:
    @agent.tool
    async def display(ctx: RunContext[Deps], artifact_id: str, rows: int = 5) -> str:
        """
        Display the first N rows of a stored artifact.

        Args:
            artifact_id: Artifact ID to display
            rows: Number of rows to display (default: 5, max: 20)
        """
        rows = min(rows, 20)
        df = ctx.deps.artifact_store.get_dataframe(ctx.deps.run_id, artifact_id)
        if df is None:
            raise ModelRetry(
                f"Error: {artifact_id} is not a valid artifact reference."
            )
        return f"Contents (first {rows} rows):\n{df.head(rows).to_string()}"

    @agent.tool
    async def run_duckdb(ctx: RunContext[Deps], artifact_id: str, sql: str) -> str:
        """
        Run a DuckDB SQL query on a stored DataFrame.

        Use this for data analysis operations like aggregations, filtering, etc.
        The virtual table name in the SQL must be 'dataset'.
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
        except Exception as exc:
            return f"Error executing DuckDB query: {exc}"
