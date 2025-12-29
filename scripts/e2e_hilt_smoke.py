#!/usr/bin/env python3
"""
Manual end-to-end smoke test for HITL flows.
This test validates:
- approval requested → deny → conversation continues
- approval requested → approve → tool executes → artifact appears
- export_csv → approval → tool-input-available → client result → conversation continues

Requires the backend server running with a configured LLM provider.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
from typing import Any
from urllib.parse import urlparse


def _make_connection(base_url: str) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlparse(base_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "localhost"
    port = parsed.port
    path_prefix = parsed.path.rstrip("/")

    if scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, port=port, timeout=60
        )
    else:
        conn = http.client.HTTPConnection(host, port=port, timeout=60)

    return conn, path_prefix


def _read_sse_chunks(resp: http.client.HTTPResponse) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for raw_line in resp:
        line = raw_line.decode("utf-8").strip()
        if not line:
            continue
        if line.startswith("data:"):
            data = line[5:].strip()
        else:
            data = line
        if data == "[DONE]":
            continue
        try:
            chunks.append(json.loads(data))
        except json.JSONDecodeError:
            continue
    return chunks


def summarize_chunks(chunks: list[dict[str, Any]]) -> str:
    types: list[str] = []
    tool_names: list[str] = []
    errors: list[str] = []
    last_content: str | None = None

    for chunk in chunks:
        chunk_type = chunk.get("type")
        if isinstance(chunk_type, str):
            types.append(chunk_type)
        if chunk_type == "tool_call":
            tool_name = chunk.get("toolCall", {}).get("function", {}).get("name")
            if isinstance(tool_name, str):
                tool_names.append(tool_name)
        if chunk_type == "approval-requested":
            tool_name = chunk.get("toolName")
            if isinstance(tool_name, str):
                tool_names.append(tool_name)
        if chunk_type == "error":
            error_msg = chunk.get("error", {}).get("message")
            if isinstance(error_msg, str):
                errors.append(error_msg)
        if chunk_type == "content":
            content = chunk.get("content")
            if isinstance(content, str):
                last_content = content

    summary = f"chunk types={types}"
    if tool_names:
        summary += f", toolNames={tool_names}"
    if errors:
        summary += f", errors={errors}"
    if last_content:
        summary += f", last_content={last_content!r}"
    return summary


def post_chat(base_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    conn, prefix = _make_connection(base_url)
    path = f"{prefix}/api/chat"
    body = json.dumps(payload).encode("utf-8")
    conn.request(
        "POST",
        path,
        body=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    resp = conn.getresponse()
    if resp.status != 200:
        raise RuntimeError(f"POST {path} failed: {resp.status} {resp.reason}")
    chunks = _read_sse_chunks(resp)
    conn.close()
    return chunks


def get_json(base_url: str, path: str) -> dict[str, Any]:
    conn, prefix = _make_connection(base_url)
    full_path = f"{prefix}{path}"
    conn.request("GET", full_path)
    resp = conn.getresponse()
    data = resp.read()
    if resp.status != 200:
        raise RuntimeError(f"GET {full_path} failed: {resp.status} {resp.reason}")
    conn.close()
    return json.loads(data)


def find_chunk(
    chunks: list[dict[str, Any]],
    chunk_type: str,
    tool_name: str | None = None,
) -> dict[str, Any] | None:
    for chunk in chunks:
        if chunk.get("type") != chunk_type:
            continue
        if tool_name and chunk.get("toolName") != tool_name:
            continue
        return chunk
    return None


def extract_run_id(chunks: list[dict[str, Any]]) -> str:
    for chunk in chunks:
        run_id = chunk.get("id")
        if isinstance(run_id, str) and run_id:
            return run_id
    raise RuntimeError("No run_id found in stream chunks.")


def parse_tool_result_envelope(content: str) -> dict[str, Any]:
    payload = json.loads(content)
    if payload.get("type") != "tool_result" or payload.get("version") != 1:
        raise RuntimeError("Tool result does not match expected envelope.")
    return payload


def assert_has_done(chunks: list[dict[str, Any]], label: str) -> None:
    if not any(chunk.get("type") == "done" for chunk in chunks):
        raise RuntimeError(f"{label}: expected done chunk, got none.")


def scenario_deny(base_url: str) -> None:
    prompt = (
        "Call execute_sql with this SQL and wait for approval: "
        "SELECT * FROM records WHERE level = 'error' LIMIT 5. "
        "If I deny, summarize next steps."
    )
    chunks = post_chat(base_url, {"messages": [{"role": "user", "content": prompt}]})
    approval = find_chunk(chunks, "approval-requested", "execute_sql")
    if not approval:
        raise RuntimeError(
            "deny: approval-requested for execute_sql not found. "
            + summarize_chunks(chunks)
        )

    run_id = extract_run_id(chunks)
    approval_id = approval.get("approval", {}).get("id")
    if not approval_id:
        raise RuntimeError("deny: approval id missing.")

    deny_chunks = post_chat(base_url, {"run_id": run_id, "approvals": {approval_id: False}})
    if not deny_chunks:
        raise RuntimeError("deny: continuation stream empty.")
    assert_has_done(deny_chunks, "deny")


def scenario_approve(base_url: str) -> None:
    prompt = (
        "Call execute_sql with this SQL and wait for approval: "
        "SELECT * FROM records WHERE level = 'error' LIMIT 5."
    )
    chunks = post_chat(base_url, {"messages": [{"role": "user", "content": prompt}]})
    approval = find_chunk(chunks, "approval-requested", "execute_sql")
    if not approval:
        raise RuntimeError(
            "approve: approval-requested for execute_sql not found. "
            + summarize_chunks(chunks)
        )

    run_id = extract_run_id(chunks)
    approval_id = approval.get("approval", {}).get("id")
    if not approval_id:
        raise RuntimeError("approve: approval id missing.")

    approve_chunks = post_chat(base_url, {"run_id": run_id, "approvals": {approval_id: True}})
    tool_result = find_chunk(approve_chunks, "tool_result")
    if not tool_result:
        raise RuntimeError("approve: tool_result chunk not found.")
    envelope = parse_tool_result_envelope(tool_result.get("content", ""))
    artifacts = envelope.get("artifacts") or []
    if not artifacts or not isinstance(artifacts, list):
        raise RuntimeError("approve: missing artifacts in tool result envelope.")
    artifact_id = artifacts[0].get("id")
    if not artifact_id:
        raise RuntimeError("approve: artifact id missing.")

    data = get_json(base_url, f"/api/data/{run_id}/{artifact_id}")
    if not data.get("rows") or not data.get("columns"):
        raise RuntimeError("approve: artifact preview missing rows/columns.")

    assert_has_done(approve_chunks, "approve")


def scenario_export(base_url: str) -> None:
    prompt = (
        "Call execute_sql with this SQL and wait for approval: "
        "SELECT * FROM records WHERE level = 'error' LIMIT 5. "
        "After that, call export_csv and wait for approval."
    )
    chunks = post_chat(base_url, {"messages": [{"role": "user", "content": prompt}]})
    approval_sql = find_chunk(chunks, "approval-requested", "execute_sql")
    if not approval_sql:
        raise RuntimeError(
            "export: approval-requested for execute_sql not found. "
            + summarize_chunks(chunks)
        )

    run_id = extract_run_id(chunks)
    approval_id = approval_sql.get("approval", {}).get("id")
    if not approval_id:
        raise RuntimeError("export: execute_sql approval id missing.")

    after_sql = post_chat(base_url, {"run_id": run_id, "approvals": {approval_id: True}})
    approval_export = find_chunk(after_sql, "approval-requested", "export_csv")
    if not approval_export:
        raise RuntimeError(
            "export: approval-requested for export_csv not found. "
            + summarize_chunks(after_sql)
        )

    export_approval_id = approval_export.get("approval", {}).get("id")
    if not export_approval_id:
        raise RuntimeError("export: export_csv approval id missing.")

    after_export_approval = post_chat(
        base_url, {"run_id": run_id, "approvals": {export_approval_id: True}}
    )
    tool_input = find_chunk(after_export_approval, "tool-input-available", "export_csv")
    if not tool_input:
        raise RuntimeError(
            "export: tool-input-available for export_csv not found. "
            + summarize_chunks(after_export_approval)
        )

    tool_call_id = tool_input.get("toolCallId")
    if not tool_call_id:
        raise RuntimeError("export: export_csv toolCallId missing.")

    client_result = {
        "type": "tool_result",
        "version": 1,
        "message": "CSV download completed.",
        "data": {"success": True, "filename": "export.csv", "rowCount": 1},
    }
    after_client = post_chat(
        base_url, {"run_id": run_id, "tool_results": {tool_call_id: client_result}}
    )
    if not after_client:
        raise RuntimeError("export: continuation stream empty after tool_results.")
    assert_has_done(after_client, "export")


def main() -> int:
    parser = argparse.ArgumentParser(description="HITL end-to-end smoke test")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    try:
        scenario_deny(args.base_url)
        scenario_approve(args.base_url)
        scenario_export(args.base_url)
    except Exception as exc:  # pragma: no cover - manual script
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print("OK: all scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
