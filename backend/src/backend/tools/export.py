from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import CallDeferred, RunContext

from ..deps import Deps
from ._common import _tool_result

if TYPE_CHECKING:
    from pydantic_ai import Agent


def register_export_tools(agent: Agent[Deps, ...]) -> None:
    @agent.tool(requires_approval=True)
    async def export_csv(ctx: RunContext[Deps], artifact_id: str) -> str:
        """
        Export a dataset as CSV file (executed on client side).

        This tool is executed in the browser (client-side).
        The client will receive the data reference and fetch the actual data
        from /api/data/{run_id}/{artifact_id} (optionally with mode=download).
        """
        if ctx.deps.artifact_store.get_metadata(ctx.deps.run_id, artifact_id) is None:
            return _tool_result(
                "エクスポート対象のデータが見つかりませんでした。"
                "直前にクエリを実行して結果を作成してから、もう一度CSV出力してください。",
                data={"success": False},
            )

        raise CallDeferred()
