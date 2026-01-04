# Approval & Tool Execution Continuation Decision (TanStack AI + pydantic-ai)

## Purpose

This document explains the root cause and the chosen fix for the issue where
results were not rendered after `approval-requested`, and records the reasoning
behind the implementation decision.

---

## Observed Problems

- After returning `approval-requested`, the UI treated the response as `done`
  and the tool result was not rendered.
- Approval could appear in the UI, but the next stream did not start.
- The auto-continue decision in TanStack could not be satisfied due to missing state.

---

## Reference Excerpts

### Meaning of `done` and the Root of the Issue

```
TanStack AI builds the UI from a stream of chunks, and the **`done` chunk
(or a closed stream) means “this response is finished.”**

Additionally, TanStack's `StreamProcessor` treats **the end of the stream
itself** as one of the triggers for detecting completed tool calls.

So the situation usually falls into one of these:

1. **The backend closes the HTTP response immediately after sending
   `approval-requested`.**
   -> The frontend considers the response finished and cannot receive tool
   results on that stream.

2. The intended TanStack approval flow is **two-phase (see below)**, but
   the current implementation stops at “approve -> execute tool on
   pydantic-ai” and **never starts the follow-up stream on the frontend**.
   -> The tool runs, but nothing is streamed back to the UI.
```

### Two-Phase (Pattern B) and Recommended Architecture

```
### Pattern B (likely recommended): end with `done` on approval request,
then start the “next stream” after approval

This **aligns best with pydantic-ai Deferred Tools**. It is OK for the first
stream to end (`done`) at `approval-requested`. The key is to **start a second
stream after approval**.

* The UI receives `approval-requested` and calls
  `addToolApprovalResponse({ id, approved })`.
* That call triggers the **same `useChat` connection adapter** to start the
  next round, and the backend:
  * executes the tool (or retrieves an already executed result)
  * streams `tool_result` chunks (plus any follow-up assistant content)
```

```
### Recommended: Pattern B (two-phase) with the same `/chat` endpoint

* **First `/chat`**: run pydantic-ai; when a Deferred Tool is hit, return
  `tool_call` -> `approval-requested` -> `done`.
* **On approval**: the frontend calls `addToolApprovalResponse`,
  and the connection adapter posts to `/chat` again
  (`messages` + `data`).
* **Second `/chat`**: read approval from `data`, resume deferred execution,
  and return `tool_result` -> `content` -> `done`.
```

### Checklist (Consistency)

```
1. **toolCallId consistency**
   * `tool_call.toolCall.id` from phase 1 must match
   * `tool_result.toolCallId` from phase 2

2. **approvalId consistency**
   * `approval-requested` approval.id must match
   * `addToolApprovalResponse({ id })`

3. **Ensure the stream is resumed/restarted after approval**
   * Pattern A: continue the same stream
   * Pattern B: start the second HTTP stream (`messages` + `data`)
```

---

## Decision Adopted

### Decision

- **Adopt Pattern B (two-phase)**
- Avoid long-lived single streams; start a second stream after approval

### Rationale

- Aligns with pydantic-ai Deferred Tools
- Avoids long-lived HTTP/SSE connections
- Matches TanStack AI semantics for `approval-requested` + `done`

---

## Implementation Reflection

### 1) Two-Phase Continuation

- First stream returns `approval-requested` → `done`
- UI sends approval with `addToolApprovalResponse`
- Second `/api/chat` stream returns `tool_result` → `content` → `done`

### 2) UI Normalization Within Official APIs

Instead of patching TanStack internals, use `setMessages` provided by `useChat`
to **re-attach approval/output metadata** on tool-call parts.

- Re-apply approval metadata when `approval-requested` arrived
- Fill `output` on tool-calls when a `tool-result` part is present
- Ensure auto-continue can evaluate completion correctly

---

## Expected Outcomes

- Results render even when `approval-requested` is followed by `done`
- Tool execution results appear in the UI
- Better resilience to TanStack internal changes
