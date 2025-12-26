// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StreamChunk, UIMessage } from "@tanstack/ai";
import type { ContinuationState } from "../types";
import { useChatSession } from "../hooks/useChatSession";

let mockMessages: UIMessage[] = [];
let mockIsLoading = false;
let mockError: Error | null = null;
const sendMessage = vi.fn();
const addToolApprovalResponse = vi.fn().mockResolvedValue(undefined);
const addToolResult = vi.fn().mockResolvedValue(undefined);
const setMessages = vi.fn();

let capturedOnChunk: ((chunk: StreamChunk) => void) | null = null;
let capturedGetContinuationState: (() => ContinuationState) | null = null;

vi.mock("@tanstack/ai-react", () => ({
  useChat: (opts: { onChunk?: (chunk: StreamChunk) => void }) => {
    capturedOnChunk = opts?.onChunk ?? null;
    return {
      messages: mockMessages,
      sendMessage,
      addToolApprovalResponse,
      addToolResult,
      setMessages,
      isLoading: mockIsLoading,
      error: mockError,
    };
  },
}));

vi.mock("../chatConnection", () => ({
  createChatConnection: (getContinuationState: () => ContinuationState) => {
    capturedGetContinuationState = getContinuationState;
    return { connect: vi.fn() };
  },
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
  addToolApprovalResponse.mockReset();
  addToolResult.mockReset();
  setMessages.mockReset();
  capturedOnChunk = null;
  capturedGetContinuationState = null;
});

describe("useChatSession", () => {
  it("exposes pending approvals when tool_calls finish reason occurs", () => {
    mockMessages = [makeToolCallMessage()];
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.(makeDoneChunk("run-1", "tool_calls"));
    });

    expect(result.current.pendingApprovals).toHaveLength(1);
    expect(result.current.pendingApprovals[0].toolCallId).toBe("call-1");
  });

  it("queues approvals and consumes continuation state after approve", async () => {
    mockMessages = [makeToolCallMessage()];
    const { result } = renderHook(() => useChatSession());

    act(() => {
      capturedOnChunk?.(makeDoneChunk("run-1", "tool_calls"));
    });

    await act(async () => {
      await result.current.approve("call-1");
    });

    expect(addToolApprovalResponse).toHaveBeenCalledWith({
      id: "call-1",
      approved: true,
    });
    expect(setMessages).toHaveBeenCalled();

    const state1 = capturedGetContinuationState?.();
    expect(state1?.runId).toBe("run-1");
    expect(state1?.approvals).toEqual({ "call-1": true });

    const state2 = capturedGetContinuationState?.();
    expect(state2?.approvals).toEqual({});
  });

  it("queues tool results and consumes continuation state after resolve", async () => {
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

    expect(addToolResult).toHaveBeenCalledWith({
      toolCallId: "tool-1",
      tool: "export_csv",
      output: { success: true },
      state: "output-available",
      errorText: undefined,
    });

    const state1 = capturedGetContinuationState?.();
    expect(state1?.toolResults).toEqual({ "tool-1": { success: true } });

    const state2 = capturedGetContinuationState?.();
    expect(state2?.toolResults).toEqual({});
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
