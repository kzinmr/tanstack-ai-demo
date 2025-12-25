"""
Database connection and schema initialization.

Based on pydantic-ai sql-gen example.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

# Database schema for the records table
DB_SCHEMA = """
CREATE TABLE records (
    created_at timestamptz,
    start_timestamp timestamptz,
    end_timestamp timestamptz,
    trace_id text,
    span_id text,
    parent_span_id text,
    level log_level,
    span_name text,
    message text,
    attributes_json_schema text,
    attributes jsonb,
    tags text[],
    is_exception boolean,
    otel_status_message text,
    service_name text
);
"""

# SQL examples for the system prompt
SQL_EXAMPLES = [
    {
        "request": "show me records where foobar is false",
        "response": "SELECT * FROM records WHERE attributes->>'foobar' = 'false' LIMIT 100",
    },
    {
        "request": 'show me records where attributes include the key "foobar"',
        "response": "SELECT * FROM records WHERE attributes ? 'foobar' LIMIT 100",
    },
    {
        "request": "show me records from yesterday",
        "response": "SELECT * FROM records WHERE start_timestamp::date > CURRENT_TIMESTAMP - INTERVAL '1 day' LIMIT 100",
    },
    {
        "request": 'show me error records with the tag "foobar"',
        "response": "SELECT * FROM records WHERE level = 'error' and 'foobar' = ANY(tags) LIMIT 100",
    },
    {
        "request": "count error logs from yesterday",
        "response": "SELECT COUNT(*) as error_count FROM records WHERE level = 'error' AND start_timestamp::date > CURRENT_TIMESTAMP - INTERVAL '1 day'",
    },
]


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:54320/pydantic_ai_sql_gen",
    )


@asynccontextmanager
async def database_connect(
    server_dsn: str | None = None,
    database: str = "pydantic_ai_sql_gen",
) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Connect to PostgreSQL, creating the database and schema if needed.

    Args:
        server_dsn: PostgreSQL server DSN (without database name)
        database: Database name to create/connect to
    """
    if server_dsn is None:
        server_dsn = "postgresql://postgres:postgres@localhost:54320"

    # First, connect to server to check/create database
    conn = await asyncpg.connect(server_dsn)
    try:
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", database
        )
        if not db_exists:
            await conn.execute(f"CREATE DATABASE {database}")
    finally:
        await conn.close()

    # Connect to the target database
    conn = await asyncpg.connect(f"{server_dsn}/{database}")
    try:
        # Create schema if needed
        async with conn.transaction():
            if not db_exists:
                # Create log_level enum
                await conn.execute(
                    "CREATE TYPE log_level AS ENUM ('debug', 'info', 'warning', 'error', 'critical')"
                )
                # Create records table
                await conn.execute(DB_SCHEMA)

                # Insert sample data for demo
                await _insert_sample_data(conn)

        yield conn
    finally:
        await conn.close()


async def _insert_sample_data(conn: asyncpg.Connection) -> None:
    """Insert sample log records for demo purposes."""
    sample_records = [
        {
            "level": "error",
            "message": "Connection timeout to database",
            "service_name": "api-gateway",
            "tags": ["production", "critical"],
        },
        {
            "level": "error",
            "message": "Failed to process payment",
            "service_name": "payment-service",
            "tags": ["production", "payment"],
        },
        {
            "level": "warning",
            "message": "High memory usage detected",
            "service_name": "worker-service",
            "tags": ["production", "performance"],
        },
        {
            "level": "error",
            "message": "Authentication failed for user",
            "service_name": "auth-service",
            "tags": ["production", "security"],
        },
        {
            "level": "info",
            "message": "Successfully processed batch job",
            "service_name": "batch-processor",
            "tags": ["production", "batch"],
        },
        {
            "level": "error",
            "message": "Rate limit exceeded",
            "service_name": "api-gateway",
            "tags": ["production", "rate-limit"],
        },
        {
            "level": "debug",
            "message": "Cache miss for key user:123",
            "service_name": "cache-service",
            "tags": ["production", "cache"],
        },
        {
            "level": "error",
            "message": "Failed to send notification email",
            "service_name": "notification-service",
            "tags": ["production", "email"],
        },
    ]

    for i, record in enumerate(sample_records):
        await conn.execute(
            """
            INSERT INTO records (
                created_at, start_timestamp, end_timestamp,
                trace_id, span_id, level, span_name, message,
                attributes, tags, is_exception, service_name
            ) VALUES (
                NOW() - INTERVAL '1 day' + $1 * INTERVAL '1 hour',
                NOW() - INTERVAL '1 day' + $1 * INTERVAL '1 hour',
                NOW() - INTERVAL '1 day' + $1 * INTERVAL '1 hour' + INTERVAL '100 ms',
                $2, $3, $4::log_level, $5, $6,
                $7::jsonb, $8, $9, $10
            )
            """,
            i,
            f"trace-{i:04d}",
            f"span-{i:04d}",
            record["level"],
            f"{record['service_name']}.handler",
            record["message"],
            "{}",
            record["tags"],
            record["level"] == "error",
            record["service_name"],
        )


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a database connection using environment configuration."""
    db_url = get_database_url()
    # Parse DATABASE_URL to extract server DSN and database name
    # Format: postgresql://user:pass@host:port/database
    if "/" in db_url.rsplit("@", 1)[-1]:
        # Has database name in URL
        parts = db_url.rsplit("/", 1)
        server_dsn = parts[0]
        database = parts[1].split("?")[0]  # Remove query params if any
    else:
        server_dsn = db_url
        database = "pydantic_ai_sql_gen"

    async with database_connect(server_dsn=server_dsn, database=database) as conn:
        yield conn
