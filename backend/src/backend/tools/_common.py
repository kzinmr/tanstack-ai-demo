from __future__ import annotations

import json


def _tool_result(message: str, artifacts: list[dict[str, object]] | None = None) -> str:
    payload: dict[str, object] = {"message": message}
    if artifacts:
        payload["artifacts"] = artifacts
    return json.dumps(payload, ensure_ascii=False)
