from __future__ import annotations

import json

TOOL_RESULT_ENVELOPE_VERSION = 1


def _tool_result(
    message: str,
    artifacts: list[dict[str, object]] | None = None,
    data: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "type": "tool_result",
        "version": TOOL_RESULT_ENVELOPE_VERSION,
        "message": message,
    }
    if artifacts:
        payload["artifacts"] = artifacts
    if data:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False)
