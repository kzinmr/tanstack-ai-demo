from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pandas as pd
from pydantic_ai import RunContext

from ..db import DB_SCHEMA
from ..deps import Deps
from ..settings import Settings
from ._common import _tool_result

if TYPE_CHECKING:
    from pydantic_ai import Agent


FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\bUPDATE\b", "UPDATE"),
    (r"\bDELETE\b", "DELETE"),
    (r"\bDROP\b", "DROP"),
    (r"\bINSERT\b", "INSERT"),
    (r"\bALTER\b", "ALTER"),
    (r"\bTRUNCATE\b", "TRUNCATE"),
    (r"\bCREATE\b", "CREATE"),
    (r"\bGRANT\b", "GRANT"),
    (r"\bREVOKE\b", "REVOKE"),
    (r"\bEXECUTE\b", "EXECUTE"),
    (r"\bCALL\b", "CALL"),
]


def validate_sql_safety(sql: str) -> str | None:
    sql_upper = sql.upper()
    for pattern, name in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql_upper, re.IGNORECASE):
            return f"Error: {name} statements are not allowed for safety reasons."
    return None


def _enforce_limit(sql: str, max_limit: int) -> str:
    sql_upper = sql.strip().upper()
    if "LIMIT" not in sql_upper:
        return f"{sql.rstrip().rstrip(';')} LIMIT {max_limit}"

    limit_match = re.search(r"LIMIT\s+(\d+)", sql_upper)
    if limit_match:
        existing_limit = int(limit_match.group(1))
        if existing_limit > max_limit:
            return re.sub(
                r"LIMIT\s+\d+",
                f"LIMIT {max_limit}",
                sql,
                flags=re.IGNORECASE,
            )
    return sql


def register_sql_tools(agent: Agent[Deps, ...], settings: Settings) -> None:
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

        Args:
            sql: The SQL query to execute. Only SELECT queries are allowed.
                 Always include LIMIT to prevent large result sets.
        """
        if error := validate_sql_safety(sql):
            return error

        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return "Error: Only SELECT queries are allowed for safety."

        sql = _enforce_limit(sql, settings.sql_max_limit)

        try:
            rows = await ctx.deps.conn.fetch(sql)
            df = pd.DataFrame([dict(r) for r in rows])
            artifact = ctx.deps.artifact_store.store(ctx.deps.run_id, df)

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
        except Exception as exc:
            return f"SQLの実行に失敗しました: {exc}"
