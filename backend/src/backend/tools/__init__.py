from __future__ import annotations

from typing import TYPE_CHECKING

from ..settings import get_settings
from .export import register_export_tools
from .sql import register_sql_tools

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from ..deps import Deps


def register_all_tools(agent: Agent[Deps, ...]) -> None:
    settings = get_settings()
    register_sql_tools(agent, settings)
    register_export_tools(agent)
