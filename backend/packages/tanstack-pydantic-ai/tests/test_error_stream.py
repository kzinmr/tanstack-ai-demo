import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from tanstack_pydantic_ai import TanStackAIAdapter


async def _collect(stream: AsyncIterator[bytes]) -> list[bytes]:
    return [chunk async for chunk in stream]


def _parse_sse_frames(frames: list[bytes]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for frame in frames:
        text = frame.decode("utf-8")
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :].strip()
            if payload == "[DONE]":
                continue
            parsed.append(json.loads(payload))
    return parsed


def test_error_chunk_emitted_on_midstream_failure() -> None:
    async def broken_stream() -> AsyncIterator[bytes]:
        yield b"data: {\"type\": \"content\"}\n\n"
        raise RuntimeError("boom")

    result = asyncio.run(
        _collect(
            TanStackAIAdapter.stream_with_error_handling(
                broken_stream(),
                run_id="run-1",
                model="test",
            )
        )
    )

    chunks = _parse_sse_frames(result)
    types = [chunk.get("type") for chunk in chunks]
    assert "error" in types
    assert "done" in types
    error_chunk = next(chunk for chunk in chunks if chunk.get("type") == "error")
    assert error_chunk["error"]["message"] == "boom"
