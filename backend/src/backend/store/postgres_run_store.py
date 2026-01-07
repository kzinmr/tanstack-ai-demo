"""
PostgreSQL-backed run store adapter.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import TypeAdapter
from pydantic_ai import DeferredToolRequests, ModelMessage
from tanstack_pydantic_ai.shared.store import RunState

from ..ports import RunStorePort

_MESSAGES_ADAPTER = TypeAdapter(list[ModelMessage])
_PENDING_ADAPTER = TypeAdapter(DeferredToolRequests | None)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS run_store (
    run_id text PRIMARY KEY,
    model text,
    messages jsonb,
    pending jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);
"""

_UPSERT_MESSAGES_SQL = """
INSERT INTO run_store (run_id, model, messages, pending, created_at, updated_at)
VALUES ($1, $2, $3, NULL, NOW(), NOW())
ON CONFLICT (run_id) DO UPDATE SET
    model = COALESCE(EXCLUDED.model, run_store.model),
    messages = EXCLUDED.messages,
    updated_at = NOW()
RETURNING model, messages, pending;
"""

_UPSERT_PENDING_SQL = """
INSERT INTO run_store (run_id, model, messages, pending, created_at, updated_at)
VALUES ($1, $2, $3, $4, NOW(), NOW())
ON CONFLICT (run_id) DO UPDATE SET
    model = COALESCE(EXCLUDED.model, run_store.model),
    pending = EXCLUDED.pending,
    updated_at = NOW()
RETURNING model, messages, pending;
"""

_SELECT_SQL = """
SELECT model, messages, pending, updated_at
FROM run_store
WHERE run_id = $1;
"""

_DELETE_SQL = """
DELETE FROM run_store
WHERE run_id = $1;
"""

_CLEANUP_EXPIRED_SQL = """
DELETE FROM run_store
WHERE updated_at < NOW() - ($1 * INTERVAL '1 minute');
"""


class _AsyncpgRunner:
    def __init__(self, dsn: str) -> None:
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise RuntimeError(
                "asyncpg is required for PostgresRunStoreAdapter."
            ) from exc

        self._asyncpg = asyncpg
        self._dsn = dsn
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._pool = self._run(self._init_pool())

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _init_pool(self):
        pool = await self._asyncpg.create_pool(self._dsn)
        async with pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)
        return pool

    def fetchrow(self, query: str, *args: Any):
        return self._run(self._fetchrow(query, *args))

    async def _fetchrow(self, query: str, *args: Any):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    def execute(self, query: str, *args: Any):
        return self._run(self._execute(query, *args))

    async def _execute(self, query: str, *args: Any):
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)


class PostgresRunStoreAdapter(RunStorePort):
    """PostgreSQL-backed run store for stateful continuation."""

    def __init__(
        self,
        dsn: str,
        *,
        ttl_minutes: int | None = None,
        max_messages: int | None = None,
    ) -> None:
        if not dsn:
            raise ValueError("Postgres run store requires a database URL.")
        self._runner = _AsyncpgRunner(dsn)
        self._ttl_minutes = (
            ttl_minutes if ttl_minutes is not None and ttl_minutes > 0 else None
        )
        self._ttl = (
            timedelta(minutes=self._ttl_minutes)
            if self._ttl_minutes is not None
            else None
        )
        self._max_messages = max_messages if max_messages and max_messages > 0 else None

    @staticmethod
    def _to_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def _maybe_json(cls, payload: Any) -> str | None:
        if payload is None:
            return None
        return cls._to_json(payload)

    def _apply_max_messages(
        self, messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        if self._max_messages is None:
            return messages
        return messages[-self._max_messages :]

    def _is_expired(self, updated_at: datetime | None) -> bool:
        if self._ttl is None or updated_at is None:
            return False
        if updated_at.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(tz=updated_at.tzinfo or timezone.utc)
        return now - updated_at > self._ttl

    def cleanup_expired(self) -> int:
        if self._ttl_minutes is None:
            return 0
        result = self._runner.execute(_CLEANUP_EXPIRED_SQL, self._ttl_minutes)
        try:
            return int(str(result).split()[-1])
        except (IndexError, ValueError):
            return 0

    def _row_to_state(
        self,
        row: Any,
        *,
        fallback_messages: list[ModelMessage] | None = None,
        fallback_pending: DeferredToolRequests | None = None,
        fallback_model: str | None = None,
    ) -> RunState:
        if row is None:
            return RunState(
                messages=fallback_messages or [],
                pending=fallback_pending,
                model=fallback_model,
            )

        messages_payload = row["messages"]
        pending_payload = row["pending"]
        model = row["model"]

        if isinstance(messages_payload, str):
            messages = _MESSAGES_ADAPTER.validate_json(messages_payload)
        else:
            messages = _MESSAGES_ADAPTER.validate_python(messages_payload or [])

        if pending_payload is None:
            pending = None
        elif isinstance(pending_payload, str):
            pending = _PENDING_ADAPTER.validate_json(pending_payload)
        else:
            pending = _PENDING_ADAPTER.validate_python(pending_payload)
        return RunState(messages=messages, pending=pending, model=model)

    def get(self, run_id: str) -> RunState | None:
        row = self._runner.fetchrow(_SELECT_SQL, run_id)
        if row is None:
            return None
        if self._is_expired(row["updated_at"]):
            self._runner.execute(_DELETE_SQL, run_id)
            return None
        return self._row_to_state(row)

    def set_messages(
        self, run_id: str, messages: list[ModelMessage], model: str | None
    ) -> RunState:
        self.cleanup_expired()
        trimmed_messages = self._apply_max_messages(messages)
        payload = _MESSAGES_ADAPTER.dump_python(trimmed_messages, mode="json")
        row = self._runner.fetchrow(
            _UPSERT_MESSAGES_SQL, run_id, model, self._to_json(payload)
        )
        return self._row_to_state(
            row,
            fallback_messages=trimmed_messages,
            fallback_model=model,
        )

    def set_pending(
        self,
        run_id: str,
        pending: DeferredToolRequests | None,
        model: str | None,
    ) -> RunState:
        self.cleanup_expired()
        messages_payload = _MESSAGES_ADAPTER.dump_python([], mode="json")
        pending_payload = _PENDING_ADAPTER.dump_python(pending, mode="json")
        row = self._runner.fetchrow(
            _UPSERT_PENDING_SQL,
            run_id,
            model,
            self._to_json(messages_payload),
            self._maybe_json(pending_payload),
        )
        return self._row_to_state(
            row,
            fallback_messages=[],
            fallback_pending=pending,
            fallback_model=model,
        )

    def clear(self, run_id: str) -> None:
        self._runner.execute(_DELETE_SQL, run_id)
