"""
RunContext dependencies for the agent.

Based on pydantic-ai data-analyst example.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from .ports import ArtifactStorePort


@dataclass
class Deps:
    """
    Dependencies for the SQL analysis agent.

    Attributes:
        conn: Database connection for executing SQL queries
        run_id: Unique identifier for this run (used for scoping artifacts)
        artifact_store: Global artifact store for this run
    """

    conn: asyncpg.Connection
    run_id: str
    artifact_store: ArtifactStorePort
