import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@tanstack/ai-react";
import type { StreamChunk, UIMessage } from "@tanstack/ai";
import type { ApprovalInfo, ClientToolInfo, ContinuationState, ToolResultPayload } from "../types";
import { createChatConnection } from "../chatConnection";
import { parseToolArguments } from "../utils/parsing";

function collectPendingApprovals(
  messages: UIMessage[],
  approvalRequests: Record<string, ApprovalInfo>
): ApprovalInfo[] {
  const approvals: ApprovalInfo[] = [];
  const pendingToolCallIds = new Set<string>();
  const resolvedToolCallIds = new Set<string>();
  const toolResultIds = new Set<string>();

  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type === "tool-result") {
        toolResultIds.add(part.toolCallId);
      }
    }
  }

  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== "tool-call") continue;
      if (part.approval?.approved !== undefined) {
        resolvedToolCallIds.add(part.id);
      }
      if (toolResultIds.has(part.id)) {
        resolvedToolCallIds.add(part.id);
      }

      const needsApproval = part.state === "approval-requested" || part.approval?.needsApproval;
      if (!needsApproval) continue;
      if (part.approval?.approved !== undefined) continue;
      if (toolResultIds.has(part.id)) continue;

      const approvalRequest = approvalRequests[part.id];
      approvals.push({
        id: part.approval?.id ?? approvalRequest?.id ?? part.id,
        toolCallId: part.id,
        toolName: part.name,
        input: parseToolArguments(part.arguments),
        runId: approvalRequest?.runId,
      });
      pendingToolCallIds.add(part.id);
    }
  }

  for (const approval of Object.values(approvalRequests)) {
    if (pendingToolCallIds.has(approval.toolCallId)) continue;
    if (resolvedToolCallIds.has(approval.toolCallId)) continue;
    if (toolResultIds.has(approval.toolCallId)) continue;
    approvals.push(approval);
  }

  return approvals;
}

function normalizeToolCallParts(
  messages: UIMessage[],
  approvalRequests: Record<string, ApprovalInfo>
): { messages: UIMessage[]; changed: boolean } {
  // Ensure tool-call parts keep approval/output metadata so auto-continue can run.
  let changed = false;

  const nextMessages = messages.map((message) => {
    if (message.role !== "assistant") return message;

    const toolResultIds = new Set<string>();
    for (const part of message.parts) {
      if (part.type === "tool-result") {
        toolResultIds.add(part.toolCallId);
      }
    }

    let partsChanged = false;
    const nextParts = message.parts.map((part) => {
      if (part.type !== "tool-call") return part;

      let updatedPart = part;
      const approvalRequest = approvalRequests[part.id];

      if (!part.approval && approvalRequest) {
        updatedPart = {
          ...updatedPart,
          approval: {
            id: approvalRequest.id,
            needsApproval: true,
          },
          state: "approval-requested",
        };
      }

      if (!updatedPart.approval && updatedPart.output === undefined && toolResultIds.has(part.id)) {
        updatedPart = {
          ...updatedPart,
          output: true,
        };
      }

      if (updatedPart !== part) {
        partsChanged = true;
      }

      return updatedPart;
    });

    if (!partsChanged) return message;
    changed = true;
    return { ...message, parts: nextParts };
  });

  return { messages: nextMessages, changed };
}

export function useChatSession() {
  const [inputText, setInputText] = useState("");
  const [pendingClientTool, setPendingClientTool] = useState<ClientToolInfo | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [approvalRequests, setApprovalRequests] = useState<Record<string, ApprovalInfo>>({});

  const continuationRef = useRef<ContinuationState>({
    pending: false,
    runId: null,
    approvals: {},
    toolResults: {},
  });

  const [messageRunIdMap, setMessageRunIdMap] = useState<Record<string, string>>({});

  const getContinuationState = useCallback((): ContinuationState => {
    const snapshot = {
      pending: continuationRef.current.pending,
      runId: continuationRef.current.runId,
      approvals: { ...continuationRef.current.approvals },
      toolResults: { ...continuationRef.current.toolResults },
    };

    const hasApprovals = Object.keys(snapshot.approvals).length > 0;
    const hasToolResults = Object.keys(snapshot.toolResults).length > 0;
    const shouldConsume = snapshot.pending && !!snapshot.runId && (hasApprovals || hasToolResults);

    if (shouldConsume) {
      continuationRef.current = {
        ...continuationRef.current,
        pending: false,
        approvals: {},
        toolResults: {},
      };
    }

    return snapshot;
  }, []);

  const connection = useMemo(
    () => createChatConnection(getContinuationState),
    [getContinuationState]
  );

  const handleChunk = useCallback((chunk: StreamChunk) => {
    if (chunk.id) {
      if (chunk.id !== continuationRef.current.runId) {
        continuationRef.current.runId = chunk.id;
      }
      setCurrentRunId((prev) => (prev === chunk.id ? prev : chunk.id));
    }

    if (chunk.type === "tool-input-available") {
      setPendingClientTool({
        toolCallId: chunk.toolCallId,
        toolName: chunk.toolName,
        input: chunk.input,
        runId: chunk.id,
      });
    }

    if (chunk.type === "approval-requested") {
      setApprovalRequests((prev) => ({
        ...prev,
        [chunk.toolCallId]: {
          id: chunk.approval?.id ?? chunk.toolCallId,
          toolCallId: chunk.toolCallId,
          toolName: chunk.toolName,
          input: chunk.input,
          runId: chunk.id,
        },
      }));
    }
  }, []);

  const {
    messages,
    sendMessage,
    addToolApprovalResponse,
    addToolResult,
    setMessages,
    isLoading,
    error,
  } = useChat({
    connection,
    onChunk: handleChunk,
  });

  useEffect(() => {
    if (messages.length === 0) return;
    const normalized = normalizeToolCallParts(messages, approvalRequests);
    if (normalized.changed) {
      setMessages(normalized.messages);
    }
  }, [messages, approvalRequests, setMessages]);

  useEffect(() => {
    if (!currentRunId) return;

    const newMappings: Record<string, string> = {};
    for (const msg of messages) {
      if (msg.role === "assistant" && !messageRunIdMap[msg.id]) {
        newMappings[msg.id] = currentRunId;
      }
    }

    if (Object.keys(newMappings).length > 0) {
      setMessageRunIdMap((prev) => ({ ...prev, ...newMappings }));
    }
  }, [messages, messageRunIdMap, currentRunId]);

  const pendingApprovals = useMemo(
    () => collectPendingApprovals(messages, approvalRequests),
    [messages, approvalRequests]
  );
  const pendingApprovalByToolCallId = useMemo(() => {
    const lookup: Record<string, ApprovalInfo> = {};
    for (const approval of pendingApprovals) {
      lookup[approval.toolCallId] = approval;
    }
    return lookup;
  }, [pendingApprovals]);

  const queueApproval = useCallback((approvalId: string, approved: boolean) => {
    continuationRef.current = {
      ...continuationRef.current,
      pending: true,
      approvals: {
        ...continuationRef.current.approvals,
        [approvalId]: approved,
      },
    };
  }, []);

  const clearApprovalRequest = useCallback((toolCallId: string) => {
    setApprovalRequests((prev) => {
      if (!prev[toolCallId]) return prev;
      const next = { ...prev };
      delete next[toolCallId];
      return next;
    });
  }, []);

  const queueToolResult = useCallback((toolCallId: string, output: Record<string, unknown>) => {
    continuationRef.current = {
      ...continuationRef.current,
      pending: true,
      toolResults: {
        ...continuationRef.current.toolResults,
        [toolCallId]: output,
      },
    };
  }, []);

  const submitMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return;
      setPendingClientTool(null);
      await sendMessage(text);
    },
    [isLoading, sendMessage]
  );

  const approve = useCallback(
    async (approvalId: string) => {
      const approvalInfo = pendingApprovals.find((approval) => approval.id === approvalId);
      if (approvalInfo?.runId) {
        continuationRef.current.runId = approvalInfo.runId;
      }
      if (approvalInfo) {
        clearApprovalRequest(approvalInfo.toolCallId);
      }
      const approvalKey = approvalInfo?.toolCallId ?? approvalId;
      queueApproval(approvalKey, true);
      await addToolApprovalResponse({ id: approvalId, approved: true });
    },
    [
      addToolApprovalResponse,
      clearApprovalRequest,
      pendingApprovals,
      queueApproval,
    ]
  );

  const deny = useCallback(
    async (approvalId: string) => {
      const approvalInfo = pendingApprovals.find((approval) => approval.id === approvalId);
      if (approvalInfo?.runId) {
        continuationRef.current.runId = approvalInfo.runId;
      }
      if (approvalInfo) {
        clearApprovalRequest(approvalInfo.toolCallId);
      }
      const approvalKey = approvalInfo?.toolCallId ?? approvalId;
      queueApproval(approvalKey, false);
      await addToolApprovalResponse({ id: approvalId, approved: false });
    },
    [
      addToolApprovalResponse,
      clearApprovalRequest,
      pendingApprovals,
      queueApproval,
    ]
  );

  const resolveClientTool = useCallback(
    async (toolCallId: string, toolName: string, payload: ToolResultPayload) => {
      queueToolResult(toolCallId, payload.output);
      setPendingClientTool(null);
      await addToolResult({
        toolCallId,
        tool: toolName,
        output: payload.output,
        state: payload.state,
        errorText: payload.errorText,
      });
    },
    [addToolResult, queueToolResult]
  );

  const getRunIdForMessage = useCallback(
    (messageId: string) => messageRunIdMap[messageId],
    [messageRunIdMap]
  );

  return {
    // useChat wrapper
    messages,
    inputText,
    setInputText,
    submitMessage,
    isLoading,
    error,
    // client-side tool & approval management
    pendingClientTool,
    pendingApprovals,
    pendingApprovalByToolCallId,
    approve,
    deny,
    resolveClientTool,
    // runId management
    getRunIdForMessage,
  };
}
