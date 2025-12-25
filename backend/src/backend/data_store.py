"""
Global data store for CSV export data.

This module provides a temporary storage for DataFrame data that needs to be
transferred to the client for CSV export. Since CallDeferred.metadata is not
forwarded by the tanstack-pydantic-ai adapter, we store the data here and
provide an API endpoint to retrieve it.

The data is keyed by a composite key of (run_id, dataset_ref) to prevent
collisions between different runs that may produce the same Out[n] reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# Global counter for unique Out[n] references across all runs
_global_out_counter: int = 0


def next_out_ref() -> str:
    """
    Generate a globally unique Out[n] reference.

    This ensures that Out references are unique across all runs/requests,
    preventing collisions in the global csv_data_store.

    Returns:
        Reference string like "Out[1]", "Out[2]", etc.
    """
    global _global_out_counter
    _global_out_counter += 1
    return f"Out[{_global_out_counter}]"


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

    Data is stored keyed by a composite key of (run_id, dataset_ref) and auto-expires
    after a configurable TTL.
    """

    def __init__(self, ttl_minutes: int = 30):
        self._store: dict[str, StoredData] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    @staticmethod
    def _composite_key(run_id: str, dataset_ref: str) -> str:
        """Create a composite key for scoped storage."""
        return f"{run_id}::{dataset_ref}"

    def store(
        self,
        run_id: str,
        dataset_ref: str,
        rows: list[dict[str, Any]],
        columns: list[str],
        original_row_count: int,
    ) -> str:
        """
        Store data keyed by run_id and dataset reference.

        Args:
            run_id: The run ID that produced this dataset
            dataset_ref: Dataset reference like "Out[1]"
            rows: List of row dictionaries
            columns: List of column names
            original_row_count: Original row count before limiting

        Returns:
            The dataset reference (same as input, for convenience)
        """
        self._cleanup_expired()

        key = self._composite_key(run_id, dataset_ref)
        self._store[key] = StoredData(
            rows=rows,
            columns=columns,
            original_row_count=original_row_count,
            exported_row_count=len(rows),
        )
        return dataset_ref

    def get(self, run_id: str, dataset_ref: str) -> StoredData | None:
        """
        Get stored data by run_id and dataset reference.

        Args:
            run_id: The run ID that produced this dataset
            dataset_ref: Dataset reference like "Out[1]"

        Returns:
            StoredData if found and not expired, None otherwise
        """
        self._cleanup_expired()

        key = self._composite_key(run_id, dataset_ref)
        data = self._store.get(key)
        if data is None:
            return None

        # Check if expired
        if datetime.now() - data.created_at > self._ttl:
            del self._store[key]
            return None

        return data

    def delete(self, run_id: str, dataset_ref: str) -> bool:
        """
        Delete stored data by run_id and dataset reference.

        Args:
            run_id: The run ID that produced this dataset
            dataset_ref: Dataset reference like "Out[1]"

        Returns:
            True if deleted, False if not found
        """
        key = self._composite_key(run_id, dataset_ref)
        if key in self._store:
            del self._store[key]
            return True
        return False

    def _cleanup_expired(self) -> None:
        """Remove expired entries from the store."""
        now = datetime.now()
        expired = [
            key
            for key, data in self._store.items()
            if now - data.created_at > self._ttl
        ]
        for key in expired:
            del self._store[key]


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
