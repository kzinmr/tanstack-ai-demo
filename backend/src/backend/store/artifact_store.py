"""
Artifact storage for table results.

A single global store that can be referenced across HITL continuation requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from ..settings import get_settings


@dataclass
class Artifact:
    """Stored artifact payload for a single run."""

    id: str
    type: str
    run_id: str
    dataframe: pd.DataFrame | None
    rows: list[dict[str, Any]]
    columns: list[str]
    original_row_count: int
    created_at: datetime = field(default_factory=datetime.now)


class ArtifactStore:
    """In-memory artifact store scoped by run_id with TTL eviction."""

    def __init__(self, ttl_minutes: int = 30):
        self._store: dict[str, Artifact] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._run_counters: dict[str, int] = {}

    @staticmethod
    def _composite_key(run_id: str, artifact_id: str) -> str:
        return f"{run_id}::{artifact_id}"

    def _generate_artifact_id(self, run_id: str) -> str:
        counter = self._run_counters.get(run_id, 0) + 1
        self._run_counters[run_id] = counter
        run_prefix = run_id[:8] if run_id else "unknown"
        return f"a_{run_prefix}_{counter}"

    @staticmethod
    def _serialize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        df_serializable = df.copy()
        for col in df_serializable.columns:
            if pd.api.types.is_datetime64_any_dtype(df_serializable[col]):
                df_serializable[col] = df_serializable[col].astype(str)
        return df_serializable

    def store(self, run_id: str, df: pd.DataFrame, type: str = "table") -> Artifact:
        self._cleanup_expired()

        artifact_id = self._generate_artifact_id(run_id)
        df_serializable = self._serialize_dataframe(df)
        rows = df_serializable.to_dict(orient="records")
        columns = list(df_serializable.columns)
        artifact = Artifact(
            id=artifact_id,
            type=type,
            run_id=run_id,
            dataframe=df,
            rows=rows,
            columns=columns,
            original_row_count=len(df),
        )
        self._store[self._composite_key(run_id, artifact_id)] = artifact
        return artifact

    def get(self, run_id: str, artifact_id: str) -> Artifact | None:
        self._cleanup_expired()

        key = self._composite_key(run_id, artifact_id)
        artifact = self._store.get(key)
        if artifact is None:
            return None

        if datetime.now() - artifact.created_at > self._ttl:
            del self._store[key]
            return None

        return artifact

    def get_dataframe(self, run_id: str, artifact_id: str) -> pd.DataFrame | None:
        artifact = self.get(run_id, artifact_id)
        if artifact is None:
            return None
        if artifact.dataframe is not None:
            return artifact.dataframe
        if not artifact.rows:
            return pd.DataFrame(columns=artifact.columns)
        return pd.DataFrame(artifact.rows, columns=artifact.columns)

    def list_artifacts(self, run_id: str) -> list[str]:
        self._cleanup_expired()
        prefix = f"{run_id}::"
        return [
            key.split("::", 1)[1]
            for key in self._store.keys()
            if key.startswith(prefix)
        ]

    def cleanup_expired(self) -> int:
        """Remove expired entries from the store."""
        return self._cleanup_expired()

    def _cleanup_expired(self) -> int:
        now = datetime.now()
        expired = [
            key
            for key, artifact in self._store.items()
            if now - artifact.created_at > self._ttl
        ]
        for key in expired:
            del self._store[key]
        return len(expired)


_artifact_store: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    """Get or create the global ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is None:
        settings = get_settings()
        _artifact_store = ArtifactStore(ttl_minutes=settings.csv_data_ttl_minutes)
    return _artifact_store
