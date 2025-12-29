"""
Run store adapters and factory.
"""

from __future__ import annotations

from tanstack_pydantic_ai import InMemoryRunStore

from ..ports import RunStorePort
from ..settings import get_settings


class InMemoryRunStoreAdapter(InMemoryRunStore, RunStorePort):
    """In-memory run store adapter."""


_run_store: RunStorePort | None = None


def get_run_store() -> RunStorePort:
    """Get or create the configured run store."""
    global _run_store
    if _run_store is not None:
        return _run_store

    settings = get_settings()
    backend = settings.run_store_backend
    if backend == "memory":
        _run_store = InMemoryRunStoreAdapter()
        return _run_store
    if backend == "postgres":
        from .postgres_run_store import PostgresRunStoreAdapter

        database_url = str(
            settings.run_store_database_url or settings.database_url
        )
        _run_store = PostgresRunStoreAdapter(database_url)
        return _run_store

    raise RuntimeError(
        f"Unsupported run store backend: {backend}. "
        "Provide a custom RunStorePort adapter for production."
    )
