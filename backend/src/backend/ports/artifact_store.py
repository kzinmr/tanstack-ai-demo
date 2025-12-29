"""
Port definition for artifact storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class ArtifactRef:
    """Lightweight reference returned after storing an artifact."""

    id: str
    type: str
    row_count: int


@dataclass(frozen=True)
class ArtifactPreview:
    rows: list[dict[str, Any]]
    columns: list[str]
    original_row_count: int
    exported_row_count: int


@dataclass(frozen=True)
class ArtifactDownload:
    url: str
    expires_in_seconds: int | None = None
    method: str = "GET"
    headers: dict[str, str] | None = None


class ArtifactStorePort(Protocol):
    """Interface for storing and retrieving artifacts."""

    def store_table(self, run_id: str, df: pd.DataFrame) -> ArtifactRef: ...

    def get_metadata(self, run_id: str, artifact_id: str) -> ArtifactRef | None: ...

    def get_preview(self, run_id: str, artifact_id: str) -> ArtifactPreview | None: ...

    def get_download(self, run_id: str, artifact_id: str) -> ArtifactDownload | None: ...
