import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@tanstack/ai-react";
import type { StreamChunk, ToolCallState, UIMessage } from "@tanstack/ai";
import type {
  ApprovalInfo,
  ClientToolInfo,
  ContinuationState,
  ToolResultPayload,
} from "../types";
import { createChatConnection } from "../chatConnection";
import { parseToolArguments } from "../utils/parsing";

const APPROVAL_REQUIRED_TOOLS = new Set(["execute_sql", "export_csv"]);

function hasToolResult(messages: UIMessage[], toolCallId: string): boolean {
  return messages.some((message) =>
    message.parts.some(
      (part) => part.type === "tool-result" && part.toolCallId === toolCallId
    )
  );
}

function ensureApprovalMetadata(
  messages: UIMessage[],
  toolCallId: string,
  approvalId: string
): UIMessage[] | null {
  let changed = false;

  const updated = messages.map((message) => {
    let partsChanged = false;
    const parts = message.parts.map((part) => {
      if (part.type !== "tool-call") return part;
      if (part.id !== toolCallId) return part;
      if (part.approval) return part;
      partsChanged = true;
      changed = true;
      return {
        ...part,
        state: "approval-requested" as ToolCallState,
        approval: {
          id: approvalId,
          needsApproval: true,
        },
      };
    });

    return partsChanged ? { ...message, parts } : message;
  });

  return changed ? updated : null;
}

function collectPendingApprovals(
  messages: UIMessage[],
  manualApprovalResponses: Record<string, boolean>
): ApprovalInfo[] {
  const approvals: ApprovalInfo[] = [];

  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== "tool-call") continue;
      if (part.approval?.needsApproval) {
        if (part.approval.approved !== undefined) continue;
        approvals.push({
          id: part.approval.id,
          toolCallId: part.id,
          toolName: part.name,
          input: parseToolArguments(part.arguments),
        });
        continue;
      }

      if (!APPROVAL_REQUIRED_TOOLS.has(part.name)) continue;
      if (part.state !== "input-complete") continue;
      if (manualApprovalResponses[part.id] !== undefined) continue;
      if (hasToolResult(messages, part.id)) continue;

      approvals.push({
        id: part.id,
        toolCallId: part.id,
        toolName: part.name,
        input: parseToolArguments(part.arguments),
      });
    }
  }

  return approvals;
}

export function useChatSession() {
  const [inputText, setInputText] = useState("");
  const [pendingClientTool, setPendingClientTool] =
    useState<ClientToolInfo | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [manualApprovalResponses, setManualApprovalResponses] = useState<
    Record<string, boolean>
  >({});

  const continuationRef = useRef<ContinuationState>({
    pending: false,
    runId: null,
    approvals: {},
    toolResults: {},
  });

  const [messageRunIdMap, setMessageRunIdMap] = useState<Record<string, string>>(
    {}
  );

  const getContinuationState = useCallback((): ContinuationState => {
    const snapshot = {
      pending: continuationRef.current.pending,
      runId: continuationRef.current.runId,
      approvals: { ...continuationRef.current.approvals },
      toolResults: { ...continuationRef.current.toolResults },
    };

    const hasApprovals = Object.keys(snapshot.approvals).length > 0;
    const hasToolResults = Object.keys(snapshot.toolResults).length > 0;
    const shouldConsume =
      snapshot.pending && !!snapshot.runId && (hasApprovals || hasToolResults);

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
    () => collectPendingApprovals(messages, manualApprovalResponses),
    [messages, manualApprovalResponses]
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

  const queueToolResult = useCallback(
    (toolCallId: string, output: Record<string, unknown>) => {
      continuationRef.current = {
        ...continuationRef.current,
        pending: true,
        toolResults: {
          ...continuationRef.current.toolResults,
          [toolCallId]: output,
        },
      };
    },
    []
  );

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
      const approvalInfo = pendingApprovals.find(
        (approval) => approval.id === approvalId
      );
      if (approvalInfo) {
        const updated = ensureApprovalMetadata(
          messages,
          approvalInfo.toolCallId,
          approvalInfo.id
        );
        if (updated) {
          setMessages(updated);
        }
      }
      setManualApprovalResponses((prev) => ({ ...prev, [approvalId]: true }));
      queueApproval(approvalId, true);
      await addToolApprovalResponse({ id: approvalId, approved: true });
    },
    [
      addToolApprovalResponse,
      messages,
      pendingApprovals,
      queueApproval,
      setMessages,
    ]
  );

  const deny = useCallback(
    async (approvalId: string) => {
      const approvalInfo = pendingApprovals.find(
        (approval) => approval.id === approvalId
      );
      if (approvalInfo) {
        const updated = ensureApprovalMetadata(
          messages,
          approvalInfo.toolCallId,
          approvalInfo.id
        );
        if (updated) {
          setMessages(updated);
        }
      }
      setManualApprovalResponses((prev) => ({ ...prev, [approvalId]: false }));
      queueApproval(approvalId, false);
      await addToolApprovalResponse({ id: approvalId, approved: false });
    },
    [
      addToolApprovalResponse,
      messages,
      pendingApprovals,
      queueApproval,
      setMessages,
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
