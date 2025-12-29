"""
Artifact storage for table results.

A single global store that can be referenced across HITL continuation requests.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ..ports import (
    Artifact,
    ArtifactDownload,
    ArtifactPreview,
    ArtifactRef,
    ArtifactStorePort,
)
from ..settings import get_settings


class InMemoryArtifactStore(ArtifactStorePort):
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

    def store_table(self, run_id: str, df: pd.DataFrame) -> ArtifactRef:
        artifact = self.store(run_id, df, type="table")
        return ArtifactRef(
            id=artifact.id,
            type=artifact.type,
            row_count=artifact.original_row_count,
        )

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

    def get_metadata(self, run_id: str, artifact_id: str) -> ArtifactRef | None:
        artifact = self.get(run_id, artifact_id)
        if artifact is None:
            return None
        return ArtifactRef(
            id=artifact.id,
            type=artifact.type,
            row_count=artifact.original_row_count,
        )

    def get_preview(self, run_id: str, artifact_id: str) -> ArtifactPreview | None:
        artifact = self.get(run_id, artifact_id)
        if artifact is None:
            return None
        rows = artifact.rows
        return ArtifactPreview(
            rows=rows,
            columns=artifact.columns,
            original_row_count=artifact.original_row_count,
            exported_row_count=len(rows),
        )

    def get_download(self, run_id: str, artifact_id: str) -> ArtifactDownload | None:
        return None

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


_artifact_store: ArtifactStorePort | None = None


def get_artifact_store() -> ArtifactStorePort:
    """Get or create the configured ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is not None:
        return _artifact_store

    settings = get_settings()
    backend = settings.artifact_store_backend
    if backend == "memory":
        _artifact_store = InMemoryArtifactStore(
            ttl_minutes=settings.csv_data_ttl_minutes
        )
        return _artifact_store
    elif backend == "s3":
        from .s3_artifact_store import S3ArtifactStore

        _artifact_store = S3ArtifactStore(
            bucket=settings.s3_bucket or "",
            prefix=settings.s3_prefix,
            region=settings.s3_region,
            url_expires_in=settings.s3_signed_url_expires_in,
            preview_rows=settings.s3_preview_rows,
            endpoint_url=settings.s3_endpoint_url,
            use_path_style=settings.s3_use_path_style,
        )
        return _artifact_store

    raise RuntimeError(f"Unsupported artifact store backend: {backend}.")
