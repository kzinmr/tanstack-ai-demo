// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StreamChunk, UIMessage } from "@tanstack/ai";
import { useChatSession } from "../hooks/useChatSession";

let mockMessages: UIMessage[] = [];
let mockIsLoading = false;
let mockError: Error | null = null;
const sendMessage = vi.fn();
const postContinuation = vi.fn().mockResolvedValue(undefined);

let capturedOnChunk: ((chunk: StreamChunk) => void) | null = null;
let capturedGetRunId: (() => string | null) | null = null;

vi.mock("@tanstack/ai-react", () => ({
  useChat: (opts: { onChunk?: (chunk: StreamChunk) => void }) => {
    capturedOnChunk = opts?.onChunk ?? null;
    return {
      messages: mockMessages,
      sendMessage,
      isLoading: mockIsLoading,
      error: mockError,
    };
  },
}));

vi.mock("../chatConnection", () => ({
  createChatConnection: (getRunId: () => string | null) => {
    capturedGetRunId = getRunId;
    return { connect: vi.fn() };
  },
}));

vi.mock("../services/dataService", () => ({
  postContinuation,
}));

function makeDoneChunk(
  runId: string,
  finishReason: "tool_calls" | "stop" = "tool_calls"
): StreamChunk {
  return {
    type: "done",
    id: runId,
    model: "test-model",
    timestamp: 0,
    finishReason,
  };
}

function makeApprovalChunk(runId: string): StreamChunk {
  return {
    type: "approval-requested",
    id: runId,
    model: "test-model",
    timestamp: 0,
    toolCallId: "call-1",
    toolName: "execute_sql",
    input: { sql: "SELECT 1" },
    approval: { id: "call-1", needsApproval: true },
  };
}

function makeToolCallMessage(): UIMessage {
  return {
    id: "assistant-1",
    role: "assistant",
    parts: [
      {
        type: "tool-call",
        id: "call-1",
        name: "execute_sql",
        arguments: "{\"sql\":\"SELECT 1\"}",
        state: "input-complete",
      },
    ],
  };
}

beforeEach(() => {
  mockMessages = [];
  mockIsLoading = false;
  mockError = null;
  sendMessage.mockReset();
  postContinuation.mockReset();
  capturedOnChunk = null;
  capturedGetRunId = null;
});

describe("useChatSession", () => {
  it("exposes pending approvals when approval-requested chunk arrives", () => {
    mockMessages = [makeToolCallMessage()];
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.(makeApprovalChunk("run-1"));
    });

    expect(capturedGetRunId?.()).toBe("run-1");
    expect(result.current.pendingApprovals).toHaveLength(1);
    expect(result.current.pendingApprovals[0].toolCallId).toBe("call-1");
    expect(result.current.pendingApprovals[0].input).toEqual({
      sql: "SELECT 1",
    });
  });

  it("queues approvals and consumes continuation state after approve", async () => {
    mockMessages = [makeToolCallMessage()];
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.(makeApprovalChunk("run-1"));
    });

    await act(async () => {
      await result.current.approve("call-1");
    });

    expect(postContinuation).toHaveBeenCalledWith("run-1", {
      approvals: { "call-1": true },
    });
    expect(result.current.pendingApprovals).toHaveLength(0);
  });

  it("posts tool results after resolve", async () => {
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.(makeDoneChunk("run-1", "stop"));
    });

    await act(async () => {
      await result.current.resolveClientTool("tool-1", "export_csv", {
        output: { success: true },
        state: "output-available",
      });
    });

    expect(postContinuation).toHaveBeenCalledWith("run-1", {
      toolResults: { "tool-1": { success: true } },
    });
  });

  it("sets pending client tool when tool-input-available arrives", () => {
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.({
        type: "tool-input-available",
        id: "run-1",
        model: "test-model",
        timestamp: 0,
        toolCallId: "call-2",
        toolName: "export_csv",
        input: { artifact_id: "a_run-1_1" },
      });
    });

    expect(result.current.pendingClientTool).toEqual({
      toolCallId: "call-2",
      toolName: "export_csv",
      input: { artifact_id: "a_run-1_1" },
      runId: "run-1",
    });
  });
});
