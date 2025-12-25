"""
RunContext dependencies for the agent.

Based on pydantic-ai data-analyst example.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg
import pandas as pd
from pydantic_ai import ModelRetry

from .data_store import next_out_ref


@dataclass
class Deps:
    """
    Dependencies for the SQL analysis agent.

    Attributes:
        conn: Database connection for executing SQL queries
        run_id: Unique identifier for this run (used for scoping Out[n] references)
        output: Storage for DataFrames referenced as Out[n]
    """

    conn: asyncpg.Connection
    run_id: str
    output: dict[str, pd.DataFrame] = field(default_factory=dict)

    def store(self, df: pd.DataFrame) -> str:
        """
        Store a DataFrame and return its reference.

        Args:
            df: DataFrame to store

        Returns:
            Reference string like "Out[1]"
        """
        ref = next_out_ref()  # Use global counter for unique refs across runs
        self.output[ref] = df
        return ref

    def get(self, ref: str) -> pd.DataFrame:
        """
        Get a stored DataFrame by reference.

        Args:
            ref: Reference string like "Out[1]"

        Returns:
            The stored DataFrame

        Raises:
            ModelRetry: If the reference is not valid
        """
        if ref not in self.output:
            raise ModelRetry(
                f"Error: {ref} is not a valid variable reference. "
                f"Available references: {list(self.output.keys())}"
            )
        return self.output[ref]

    def list_outputs(self) -> list[str]:
        """List all available output references."""
        return list(self.output.keys())
