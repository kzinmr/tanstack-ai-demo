# Approval & Tool Execution Continuation Decision (TanStack AI + pydantic-ai)

## Purpose

This document explains the root cause and the chosen fix for the issue where
results were not rendered after `approval-requested`, and records the reasoning
behind the implementation decision and tradeoffs.

---

## Observed Problems

- After returning `approval-requested`, the UI treated the response as `done`
  and the tool result was not rendered.
- Approval could appear in the UI, but the next stream did not start.
- The auto-continue decision in TanStack could not be satisfied due to missing state.

---

## Reference Excerpts (Context)

### Meaning of `done` and the Root of the Issue

```
TanStack AI builds the UI from a stream of chunks, and the `done` chunk
(or a closed stream) means "this response is finished."

Additionally, TanStack's StreamProcessor treats the end of the stream
itself as one of the triggers for detecting completed tool calls.
```

---

## Decision Adopted (Updated)

### Decision

- **Adopt single-stream continuation pattern**
- Keep the SSE stream open across `approval-requested` and resume in-place

### Rationale

- Aligns with TanStack AI state machine expectations (single-stream lifecycle)
- Removes the need to "reconstruct" tool-call state in the UI
- Simplifies frontend state management and reduces workarounds

---

## Design Tradeoffs

### State Machine Compatibility vs Connection Lifetime

- Single-stream continuation removes the stream-boundary mismatch and keeps
  TanStack's tool-call lifecycle consistent.
- The cost is long-lived SSE connections, keep-alives, and timeout handling.

### Simplicity in UI vs Complexity in App Layer

- Frontend complexity is reduced (no continuationRef, no message normalization).
- Backend gains responsibility for waiting and resuming (continuation hub,
  keep-alive, separate continuation endpoint).

## Implementation Tradeoffs

### What Moved to the App Layer

- `/api/chat` holds the stream open after `approval-requested`
- `/api/continuation` receives approvals/tool results
- A per-run continuation hub coordinates resume events
- SSE keep-alives prevent idle timeouts while awaiting approval

### What Was Removed from the Frontend

- `normalizeToolCallParts` and related message patching
- `continuationRef` and client-side auto-continue payload building
- Dependence on `addToolApprovalResponse` / `addToolResult` to trigger a new stream

---

## Expected Outcomes (Updated)

- Tool approval and tool results appear in the same stream as the tool call
- UI no longer needs to patch tool-call state after the fact
- Reduced frontend state complexity, at the cost of long-lived SSE management
