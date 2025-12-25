"""
Global data store for CSV export data.

This module provides a temporary storage for DataFrame data that needs to be
transferred to the client for CSV export. Since CallDeferred.metadata is not
forwarded by the tanstack-pydantic-ai adapter, we store the data here and
provide an API endpoint to retrieve it.

The data is keyed by the dataset reference (e.g., "Out[1]") since that's what
gets forwarded to the client in tool-input-available.input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class StoredData:
    """Data stored for CSV export."""

    rows: list[dict[str, Any]]
    columns: list[str]
    original_row_count: int
    exported_row_count: int
    created_at: datetime = field(default_factory=datetime.now)


class DataStore:
    """
    In-memory store for CSV export data.

    Data is stored keyed by dataset reference (e.g., "Out[1]") and auto-expires
    after a configurable TTL.
    """

    def __init__(self, ttl_minutes: int = 30):
        self._store: dict[str, StoredData] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def store(
        self,
        dataset_ref: str,
        rows: list[dict[str, Any]],
        columns: list[str],
        original_row_count: int,
    ) -> str:
        """
        Store data keyed by dataset reference.

        Args:
            dataset_ref: Dataset reference like "Out[1]"
            rows: List of row dictionaries
            columns: List of column names
            original_row_count: Original row count before limiting

        Returns:
            The dataset reference (same as input, for convenience)
        """
        self._cleanup_expired()

        self._store[dataset_ref] = StoredData(
            rows=rows,
            columns=columns,
            original_row_count=original_row_count,
            exported_row_count=len(rows),
        )
        return dataset_ref

    def get(self, dataset_ref: str) -> StoredData | None:
        """
        Get stored data by dataset reference.

        Args:
            dataset_ref: Dataset reference like "Out[1]"

        Returns:
            StoredData if found and not expired, None otherwise
        """
        self._cleanup_expired()

        data = self._store.get(dataset_ref)
        if data is None:
            return None

        # Check if expired
        if datetime.now() - data.created_at > self._ttl:
            del self._store[dataset_ref]
            return None

        return data

    def delete(self, dataset_ref: str) -> bool:
        """
        Delete stored data by dataset reference.

        Args:
            dataset_ref: Dataset reference like "Out[1]"

        Returns:
            True if deleted, False if not found
        """
        if dataset_ref in self._store:
            del self._store[dataset_ref]
            return True
        return False

    def _cleanup_expired(self) -> None:
        """Remove expired entries from the store."""
        now = datetime.now()
        expired = [
            ref
            for ref, data in self._store.items()
            if now - data.created_at > self._ttl
        ]
        for ref in expired:
            del self._store[ref]


def get_csv_data_store() -> DataStore:
    """Get the CSV data store with settings-based TTL."""
    from .settings import get_settings

    settings = get_settings()
    return DataStore(ttl_minutes=settings.csv_data_ttl_minutes)


# Global instance (lazy initialization to avoid circular imports)
_csv_data_store: DataStore | None = None


def csv_data_store() -> DataStore:
    """Get or create the global CSV data store."""
    global _csv_data_store
    if _csv_data_store is None:
        _csv_data_store = get_csv_data_store()
    return _csv_data_store
