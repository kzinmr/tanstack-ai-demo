/**
 * React hook for handling TanStack AI chat streams with HITL support.
 */

import { useCallback, useRef, useState } from "react";
import {
  sseJsonIterator,
  StreamChunk,
  ApprovalRequestedStreamChunk,
  ToolInputAvailableStreamChunk,
} from "./sse";

/**
 * A chat message.
 */
export interface UIMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Information about a pending approval request.
 */
export interface ApprovalInfo {
  toolCallId: string;
  toolName: string;
  input: unknown;
}

/**
 * Information about a pending client-side tool execution.
 */
export interface ClientToolInfo {
  toolCallId: string;
  toolName: string;
  input: {
    rows?: Record<string, unknown>[];
    columns?: string[];
    original_row_count?: number;
    exported_row_count?: number;
    [key: string]: unknown;
  };
}

/**
 * Hook options.
 */
interface UseChatStreamOptions {
  apiBase?: string;
}

/**
 * Hook return type.
 */
interface UseChatStreamReturn {
  messages: UIMessage[];
  isStreaming: boolean;
  runId: string | null;
  pendingApprovals: Map<string, ApprovalInfo>;
  pendingClientTool: ClientToolInfo | null;
  error: string | null;
  send: (text: string) => Promise<void>;
  approve: (toolCallId: string) => Promise<void>;
  deny: (toolCallId: string) => Promise<void>;
  submitClientResult: (
    toolCallId: string,
    result: Record<string, unknown>
  ) => Promise<void>;
  clearError: () => void;
}

/**
 * Hook for managing chat streams with HITL support.
 */
export function useChatStream(
  options: UseChatStreamOptions = {}
): UseChatStreamReturn {
  const { apiBase = "" } = options;

  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<
    Map<string, ApprovalInfo>
  >(new Map());
  const [pendingClientTool, setPendingClientTool] =
    useState<ClientToolInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Keep track of all messages for continuation
  const messagesRef = useRef<Array<{ role: string; content: string }>>([]);

  /**
   * Process a stream of chunks.
   */
  const processStream = useCallback(
    async (response: Response) => {
      let currentContent = "";

      for await (const chunk of sseJsonIterator(response)) {
        const typedChunk = chunk as StreamChunk;

        // Store run_id from first chunk
        if (typedChunk.id && !runId) {
          setRunId(typedChunk.id);
        }

        switch (typedChunk.type) {
          case "content": {
            currentContent = typedChunk.content;
            setMessages((prev) => {
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (lastMessage?.role === "assistant") {
                newMessages[newMessages.length - 1] = {
                  role: "assistant",
                  content: currentContent,
                };
              }
              return newMessages;
            });
            break;
          }

          case "tool_call": {
            // Just log tool calls for now
            console.log("Tool call:", typedChunk.toolCall);
            break;
          }

          case "tool_result": {
            // Tool result received
            console.log("Tool result:", typedChunk.toolCallId, typedChunk.content);
            break;
          }

          case "approval-requested": {
            const approvalChunk = typedChunk as ApprovalRequestedStreamChunk;
            setPendingApprovals((prev) => {
              const next = new Map(prev);
              next.set(approvalChunk.toolCallId, {
                toolCallId: approvalChunk.toolCallId,
                toolName: approvalChunk.toolName,
                input: approvalChunk.input,
              });
              return next;
            });
            break;
          }

          case "tool-input-available": {
            const inputChunk = typedChunk as ToolInputAvailableStreamChunk;
            setPendingClientTool({
              toolCallId: inputChunk.toolCallId,
              toolName: inputChunk.toolName,
              input: inputChunk.input as ClientToolInfo["input"],
            });
            break;
          }

          case "error": {
            setError(typedChunk.error.message);
            break;
          }

          case "done": {
            // Stream finished
            if (currentContent) {
              messagesRef.current.push({
                role: "assistant",
                content: currentContent,
              });
            }
            break;
          }
        }
      }
    },
    [runId]
  );

  /**
   * Send a new message.
   */
  const send = useCallback(
    async (text: string) => {
      if (!text.trim()) return;

      setIsStreaming(true);
      setError(null);

      // Add user message
      const userMessage: UIMessage = { role: "user", content: text };
      setMessages((prev) => [...prev, userMessage]);
      messagesRef.current.push({ role: "user", content: text });

      // Add empty assistant message for streaming
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const res = await fetch(`${apiBase}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: messagesRef.current,
          }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        await processStream(res);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setError(message);
        // Remove empty assistant message on error
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsStreaming(false);
      }
    },
    [apiBase, processStream]
  );

  /**
   * Approve a tool execution.
   */
  const approve = useCallback(
    async (toolCallId: string) => {
      if (!runId) {
        setError("No run_id available for approval");
        return;
      }

      setIsStreaming(true);
      setError(null);

      // Remove from pending
      setPendingApprovals((prev) => {
        const next = new Map(prev);
        next.delete(toolCallId);
        return next;
      });

      // Add empty assistant message for streaming continuation
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const res = await fetch(`${apiBase}/api/chat/continue`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: runId,
            approvals: { [toolCallId]: true },
          }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        await processStream(res);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setError(message);
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsStreaming(false);
      }
    },
    [apiBase, runId, processStream]
  );

  /**
   * Deny a tool execution.
   */
  const deny = useCallback(
    async (toolCallId: string) => {
      if (!runId) {
        setError("No run_id available for denial");
        return;
      }

      setIsStreaming(true);
      setError(null);

      // Remove from pending
      setPendingApprovals((prev) => {
        const next = new Map(prev);
        next.delete(toolCallId);
        return next;
      });

      // Add empty assistant message for streaming continuation
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const res = await fetch(`${apiBase}/api/chat/continue`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: runId,
            approvals: { [toolCallId]: false },
          }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        await processStream(res);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setError(message);
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsStreaming(false);
      }
    },
    [apiBase, runId, processStream]
  );

  /**
   * Submit client tool result.
   */
  const submitClientResult = useCallback(
    async (toolCallId: string, result: Record<string, unknown>) => {
      if (!runId) {
        setError("No run_id available for tool result");
        return;
      }

      setIsStreaming(true);
      setError(null);

      // Clear pending client tool
      setPendingClientTool(null);

      // Add empty assistant message for streaming continuation
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const res = await fetch(`${apiBase}/api/chat/continue`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: runId,
            tool_results: { [toolCallId]: result },
          }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        await processStream(res);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setError(message);
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsStreaming(false);
      }
    },
    [apiBase, runId, processStream]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    messages,
    isStreaming,
    runId,
    pendingApprovals,
    pendingClientTool,
    error,
    send,
    approve,
    deny,
    submitClientResult,
    clearError,
  };
}
