import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@tanstack/ai-react";
import type { StreamChunk } from "@tanstack/ai";
import type { ApprovalInfo, ClientToolInfo, ToolResultPayload } from "../types";
import { createChatConnection } from "../chatConnection";
import { postContinuation } from "../services/dataService";
import { parseToolArguments } from "../utils/parsing";

export function useChatSession() {
  const [inputText, setInputText] = useState("");
  const [pendingClientTool, setPendingClientTool] = useState<ClientToolInfo | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [approvalRequests, setApprovalRequests] = useState<Record<string, ApprovalInfo>>({});
  const runIdRef = useRef<string | null>(null);
  const [isContinuing, setIsContinuing] = useState(false);

  const [messageRunIdMap, setMessageRunIdMap] = useState<Record<string, string>>({});

  const getRunId = useCallback(() => runIdRef.current, []);
  const connection = useMemo(() => createChatConnection(getRunId), [getRunId]);

  const handleChunk = useCallback((chunk: StreamChunk) => {
    if (chunk.id) {
      if (chunk.id !== runIdRef.current) {
        runIdRef.current = chunk.id;
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
      const input = typeof chunk.input === "string" ? parseToolArguments(chunk.input) : chunk.input;
      setApprovalRequests((prev) => ({
        ...prev,
        [chunk.toolCallId]: {
          id: chunk.approval?.id ?? chunk.toolCallId,
          toolCallId: chunk.toolCallId,
          toolName: chunk.toolName,
          input,
          runId: chunk.id,
        },
      }));
    }

    if (chunk.type === "tool_result") {
      setApprovalRequests((prev) => {
        if (!prev[chunk.toolCallId]) return prev;
        const next = { ...prev };
        delete next[chunk.toolCallId];
        return next;
      });
    }
  }, [isContinuing]);

  const {
    messages,
    sendMessage,
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
    () => Object.values(approvalRequests),
    [approvalRequests]
  );
  const pendingApprovalByToolCallId = approvalRequests;

  const clearApprovalRequest = useCallback((toolCallId: string) => {
    setApprovalRequests((prev) => {
      if (!prev[toolCallId]) return prev;
      const next = { ...prev };
      delete next[toolCallId];
      return next;
    });
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
      if (isContinuing) return;
      const approvalInfo = pendingApprovals.find((approval) => approval.id === approvalId);
      if (approvalInfo) {
        clearApprovalRequest(approvalInfo.toolCallId);
      }
      const runId = approvalInfo?.runId ?? runIdRef.current;
      if (!runId) return;
      const approvalKey = approvalInfo?.toolCallId ?? approvalId;
      setIsContinuing(true);
      try {
        await postContinuation(runId, { approvals: { [approvalKey]: true } });
      } finally {
        setIsContinuing(false);
      }
    },
    [
      clearApprovalRequest,
      isContinuing,
      pendingApprovals,
    ]
  );

  const deny = useCallback(
    async (approvalId: string) => {
      if (isContinuing) return;
      const approvalInfo = pendingApprovals.find((approval) => approval.id === approvalId);
      if (approvalInfo) {
        clearApprovalRequest(approvalInfo.toolCallId);
      }
      const runId = approvalInfo?.runId ?? runIdRef.current;
      if (!runId) return;
      const approvalKey = approvalInfo?.toolCallId ?? approvalId;
      setIsContinuing(true);
      try {
        await postContinuation(runId, { approvals: { [approvalKey]: false } });
      } finally {
        setIsContinuing(false);
      }
    },
    [
      clearApprovalRequest,
      isContinuing,
      pendingApprovals,
    ]
  );

  const resolveClientTool = useCallback(
    async (toolCallId: string, _toolName: string, payload: ToolResultPayload) => {
      if (isContinuing) return;
      const runId = runIdRef.current;
      if (!runId) return;
      setPendingClientTool(null);
      setIsContinuing(true);
      try {
        await postContinuation(runId, { toolResults: { [toolCallId]: payload.output } });
      } finally {
        setIsContinuing(false);
      }
    },
    [isContinuing]
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
    isContinuing,
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
