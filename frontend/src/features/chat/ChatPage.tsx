/**
 * Main chat page component.
 */

import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Input } from "@base-ui/react/input";
import { Button } from "@base-ui/react/button";
import { useChat } from "@tanstack/ai-react";
import type {
  MessagePart,
  StreamChunk,
  ToolCallPart,
  ToolCallState,
  ToolResultPart,
  UIMessage,
} from "@tanstack/ai";
import { ApprovalCard, type ApprovalInfo } from "./ApprovalCard";
import {
  ToolInputPanel,
  type ClientToolInfo,
  type ToolResultPayload,
} from "./ToolInputPanel";
import { createChatConnection } from "./chatConnection";

type ContinuationState = {
  pending: boolean;
  runId: string | null;
  approvals: Record<string, boolean>;
  toolResults: Record<string, unknown>;
};

function parseToolArguments(argumentsText: string): unknown {
  if (!argumentsText) return {};
  try {
    return JSON.parse(argumentsText);
  } catch {
    return argumentsText;
  }
}

function formatToolArguments(argumentsText: string): string {
  if (!argumentsText) return "{}";
  try {
    return JSON.stringify(JSON.parse(argumentsText), null, 2);
  } catch {
    return argumentsText;
  }
}

function hasPendingApproval(parts: MessagePart[]): boolean {
  return parts.some(
    (part) => {
      if (part.type !== "tool-call") return false;
      if (part.approval?.needsApproval && part.approval.approved === undefined) {
        return true;
      }
      return (
        !part.approval &&
        part.state === "input-complete" &&
        APPROVAL_REQUIRED_TOOLS.has(part.name)
      );
    }
  );
}

function extractDatasetRef(parts: MessagePart[]): string | null {
  const pattern = /Out\[\d+\]/g;

  const findFirst = (text: string): string | null => {
    const match = text.match(pattern);
    return match?.[0] ?? null;
  };

  for (const part of parts) {
    if (part.type === "tool-result") {
      const found = findFirst(part.content);
      if (found) return found;
    }
  }

  if (hasPendingApproval(parts)) {
    return null;
  }

  for (const part of parts) {
    if (part.type === "text") {
      const found = findFirst(part.content);
      if (found) return found;
    }
  }

  return null;
}

const APPROVAL_REQUIRED_TOOLS = new Set(["execute_sql", "export_csv"]);

function hasToolResult(
  messages: UIMessage[],
  toolCallId: string
): boolean {
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

export function ChatPage() {
  const [inputText, setInputText] = useState("");
  const [pendingClientTool, setPendingClientTool] =
    useState<ClientToolInfo | null>(null);
  const [visibleError, setVisibleError] = useState<Error | null>(null);
  const [manualApprovalResponses, setManualApprovalResponses] = useState<
    Record<string, boolean>
  >({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const continuationRef = useRef<ContinuationState>({
    pending: false,
    runId: null,
    approvals: {},
    toolResults: {},
  });

  // Track which runId each message belongs to (for scoped data fetching)
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
    if (chunk.id && chunk.id !== continuationRef.current.runId) {
      continuationRef.current.runId = chunk.id;
    }

    if (chunk.type === "tool-input-available") {
      setPendingClientTool({
        toolCallId: chunk.toolCallId,
        toolName: chunk.toolName,
        input: chunk.input,
        runId: chunk.id,  // Include run_id for scoped data fetch
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
    setVisibleError(error ?? null);
  }, [error]);

  // Associate assistant messages with their runId for scoped data fetching
  useEffect(() => {
    const currentRunId = continuationRef.current.runId;
    if (!currentRunId) return;

    // Find assistant messages that don't have a runId mapping yet
    const newMappings: Record<string, string> = {};
    for (const msg of messages) {
      if (msg.role === "assistant" && !messageRunIdMap[msg.id]) {
        newMappings[msg.id] = currentRunId;
      }
    }

    if (Object.keys(newMappings).length > 0) {
      setMessageRunIdMap((prev) => ({ ...prev, ...newMappings }));
    }
  }, [messages, messageRunIdMap]);

  const pendingApprovals = useMemo(
    () => collectPendingApprovals(messages, manualApprovalResponses),
    [messages, manualApprovalResponses]
  );
  const currentApproval = pendingApprovals[0] ?? null;
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

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingClientTool, currentApproval]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading) return;

    const text = inputText;
    setInputText("");
    setPendingClientTool(null);
    await sendMessage(text);
  };

  const handleApprove = async (approvalId: string) => {
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
  };

  const handleDeny = async (approvalId: string) => {
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
  };

  const handleClientResult = async (
    toolCallId: string,
    toolName: string,
    payload: ToolResultPayload
  ) => {
    queueToolResult(toolCallId, payload.output);
    setPendingClientTool(null);
    await addToolResult({
      toolCallId,
      tool: toolName,
      output: payload.output,
      state: payload.state,
      errorText: payload.errorText,
    });
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white px-4 py-3 shadow-sm">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">
            TanStack AI HITL Demo
          </h1>
          <span className="text-sm text-gray-500">
            SQL Analysis with Human-in-the-Loop
          </span>
        </div>
      </header>

      {/* Error notification */}
      {visibleError && (
        <div className="max-w-4xl mx-auto w-full px-4 pt-4">
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
            <span>{visibleError.message}</span>
            <button
              onClick={() => setVisibleError(null)}
              className="text-red-500 hover:text-red-700 font-bold text-lg leading-none"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Messages */}
      <main className="flex-1 overflow-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <h2 className="text-xl font-medium text-gray-700 mb-2">
                Welcome to the SQL Analysis Demo
              </h2>
              <p className="text-gray-500 mb-6">
                Ask questions about your log data. I'll help you analyze it with
                SQL.
              </p>
              <div className="bg-white rounded-lg p-4 text-left max-w-lg mx-auto border">
                <p className="text-sm text-gray-600 mb-2">Try this example:</p>
                <p className="text-sm text-gray-800 italic">
                  "`records` から昨日の error を集計したい。SQL
                  は作っていいけど、実行前に必ず確認させて。結果は CSV
                  でダウンロードしたいけど、それも確認してからにして。"
                </p>
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                runId={messageRunIdMap[message.id]}
                pendingApprovalByToolCallId={pendingApprovalByToolCallId}
                onApprove={handleApprove}
                onDeny={handleDeny}
                isLoading={isLoading}
              />
            ))
          )}

          {/* Tool input panel */}
          <ToolInputPanel
            clientTool={pendingClientTool}
            onComplete={handleClientResult}
            isLoading={isLoading}
          />

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Input form */}
      <footer className="border-t bg-white px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-3">
          <div className="flex-1">
            <Input
              value={inputText}
              onChange={(e) => setInputText(e.currentTarget.value)}
              placeholder="Type a message..."
              disabled={isLoading || pendingApprovals.length > 0}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
            />
          </div>
          <Button
            type="submit"
            disabled={
              !inputText.trim() || pendingApprovals.length > 0 || isLoading
            }
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading && (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            )}
            Send
          </Button>
        </form>
      </footer>

    </div>
  );
}

/**
 * Message bubble component.
 */
interface MessageBubbleProps {
  message: UIMessage;
  runId?: string;
  pendingApprovalByToolCallId: Record<string, ApprovalInfo>;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
}

function MessageBubble({
  message,
  runId,
  pendingApprovalByToolCallId,
  onApprove,
  onDeny,
  isLoading,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [datasetPreview, setDatasetPreview] = useState<{
    dataset: string;
    rows: Record<string, unknown>[];
    columns: string[];
    original_row_count: number;
    exported_row_count: number;
  } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const datasetRef = useMemo(
    () => extractDatasetRef(message.parts),
    [message.parts]
  );

  // Auto-preview the first Out[n] reference in assistant messages (if available).
  useEffect(() => {
    if (isUser) return;

    if (!datasetRef || !runId) {
      setDatasetPreview(null);
      setPreviewError(null);
      return;
    }

    let cancelled = false;
    setDatasetPreview(null);
    setPreviewError(null);

    (async () => {
      try {
        const res = await fetch(
          `/api/data/${encodeURIComponent(runId)}/${encodeURIComponent(datasetRef)}`
        );
        if (!res.ok) {
          throw new Error(`Failed to fetch data: ${res.statusText}`);
        }
        const data = await res.json();
        if (!cancelled) {
          setDatasetPreview({ dataset: datasetRef, ...data });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        if (!cancelled) setPreviewError(msg);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [datasetRef, runId, isUser]);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-3 ${
          isUser
            ? "bg-gray-900 text-white"
            : "bg-white border border-gray-200 text-gray-800"
        }`}
      >
        <div className="space-y-2">
          {message.parts.length === 0 ? (
            <span className="text-gray-400 italic">Thinking...</span>
          ) : (
            message.parts.map((part, index) => (
              <MessagePartView
                key={`${part.type}-${index}`}
                part={part}
                pendingApprovalByToolCallId={pendingApprovalByToolCallId}
                onApprove={onApprove}
                onDeny={onDeny}
                isLoading={isLoading}
              />
            ))
          )}
        </div>

        {!isUser && datasetPreview && (
          <div className="mt-3 bg-gray-50 border border-gray-200 rounded p-3 overflow-auto">
            <div className="text-xs text-gray-600 mb-2">
              {datasetPreview.dataset} プレビュー（
              {datasetPreview.exported_row_count} 行 /{" "}
              {datasetPreview.columns.length} 列）
            </div>
            <table className="text-xs w-full border-collapse">
              <thead>
                <tr>
                  {datasetPreview.columns.map((c) => (
                    <th
                      key={c}
                      className="text-left border-b border-gray-200 pr-3 pb-1 font-medium"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datasetPreview.rows.slice(0, 5).map((row, i) => (
                  <tr key={i}>
                    {datasetPreview.columns.map((c) => (
                      <td
                        key={c}
                        className="pr-3 py-1 border-b border-gray-100"
                      >
                        {String((row as any)[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!isUser && previewError && (
          <div className="mt-3 text-xs text-gray-500">
            データプレビューを取得できませんでした: {previewError}
          </div>
        )}
      </div>
    </div>
  );
}

interface MessagePartViewProps {
  part: MessagePart;
  pendingApprovalByToolCallId: Record<string, ApprovalInfo>;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
}

function MessagePartView({
  part,
  pendingApprovalByToolCallId,
  onApprove,
  onDeny,
  isLoading,
}: MessagePartViewProps) {
  if (part.type === "text") {
    return <div className="text-sm whitespace-pre-wrap">{part.content}</div>;
  }

  if (part.type === "thinking") {
    return (
      <div className="text-xs text-gray-400 italic whitespace-pre-wrap">
        Thinking: {part.content}
      </div>
    );
  }

  if (part.type === "tool-call") {
    const pendingApproval = pendingApprovalByToolCallId[part.id];
    return (
      <ToolCallPartView
        part={part}
        pendingApproval={pendingApproval}
        onApprove={onApprove}
        onDeny={onDeny}
        isLoading={isLoading}
      />
    );
  }

  if (part.type === "tool-result") {
    return <ToolResultPartView part={part} />;
  }

  return null;
}

interface ToolCallPartViewProps {
  part: ToolCallPart;
  pendingApproval?: ApprovalInfo;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
}

function ToolCallPartView({
  part,
  pendingApproval,
  onApprove,
  onDeny,
  isLoading = false,
}: ToolCallPartViewProps) {
  const approvalStatus = part.approval?.approved;
  const needsApproval = part.approval?.needsApproval ?? false;
  const isPendingApproval =
    (needsApproval && approvalStatus === undefined) || !!pendingApproval;
  const approvalId = pendingApproval?.id ?? part.approval?.id;
  const approvalInput =
    pendingApproval?.input ?? parseToolArguments(part.arguments);
  const hasApprovalRequest = needsApproval || !!pendingApproval;

  // Display label for the tool call state (may differ from ToolCallState enum for UI purposes)
  let statusLabel: string = part.state;
  if (hasApprovalRequest) {
    if (approvalStatus === undefined) {
      statusLabel = "approval-requested";
    } else if (approvalStatus) {
      statusLabel = "approved";
    } else {
      statusLabel = "denied";
    }
  }

  return (
    <div>
      <div className="rounded-md border border-gray-200 bg-gray-50 p-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="font-medium text-gray-700">Tool: {part.name}</span>
          <span
            className={`${
              isPendingApproval
                ? "text-amber-600 font-medium"
                : approvalStatus === false
                  ? "text-red-500"
                  : approvalStatus === true
                    ? "text-green-600"
                    : "text-gray-500"
            }`}
          >
            {statusLabel}
          </span>
        </div>
        <pre className="mt-2 whitespace-pre-wrap text-gray-600">
          {formatToolArguments(part.arguments)}
        </pre>
      </div>

      {isPendingApproval && onApprove && onDeny && approvalId && (
        <ApprovalCard
          approvalId={approvalId}
          toolName={part.name}
          input={approvalInput}
          onApprove={onApprove}
          onDeny={onDeny}
          isLoading={isLoading}
        />
      )}
    </div>
  );
}

function ToolResultPartView({ part }: { part: ToolResultPart }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-2 text-xs">
      <div className="text-gray-500 mb-1">Tool result</div>
      <div className="whitespace-pre-wrap text-gray-700">{part.content}</div>
    </div>
  );
}
