from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pandas as pd
from pydantic_ai import RunContext
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
        Show the database schema for available tables.

        Use this to understand the structure before writing SQL queries.
        """
        try:
            enum_rows = await ctx.deps.conn.fetch(
                """
                SELECT
                    t.typname AS enum_name,
                    e.enumlabel AS enum_value,
                    e.enumsortorder AS sort_order
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE n.nspname = 'public'
                ORDER BY t.typname, e.enumsortorder
                """
            )

            enums: dict[str, list[str]] = {}
            for row in enum_rows:
                enums.setdefault(row["enum_name"], []).append(row["enum_value"])

            column_rows = await ctx.deps.conn.fetch(
                """
                SELECT
                    c.relname AS table_name,
                    a.attname AS column_name,
                    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                    a.attnotnull AS not_null,
                    a.attnum AS ordinal_position
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum
                """
            )

            if not column_rows:
                return "Database Schema:\n(no tables found)"

            tables: dict[str, list[str]] = {}
            for row in column_rows:
                table_name = row["table_name"]
                col_name = row["column_name"]
                data_type = row["data_type"]
                not_null = row["not_null"]
                col_def = f"    {col_name} {data_type}"
                if not_null:
                    col_def += " NOT NULL"
                tables.setdefault(table_name, []).append(col_def)

            schema_lines: list[str] = []
            if enums:
                enum_defs = []
                for enum_name, values in enums.items():
                    quoted = ", ".join(f"'{value}'" for value in values)
                    enum_defs.append(f"CREATE TYPE {enum_name} AS ENUM ({quoted});")
                schema_lines.append("Enum Types:\n" + "\n".join(enum_defs))

            table_defs = []
            for table_name, columns in tables.items():
                table_defs.append(
                    "CREATE TABLE "
                    f"{table_name} (\n{',\n'.join(columns)}\n);"
                )
            schema_lines.append("Tables:\n" + "\n\n".join(table_defs))

            return "Database Schema:\n" + "\n\n".join(schema_lines)
        except Exception as exc:
            return f"Failed to load schema: {exc}"

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
            return _tool_result(
                message=(
                    f"クエリを実行しました（{row_count}行）。"
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
