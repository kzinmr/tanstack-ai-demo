/**
 * Main chat page component.
 */

import { useState, useRef, useEffect } from "react";
import { Input } from "@base-ui/react/input";
import { Button } from "@base-ui/react/button";
import { useChatStream, UIMessage } from "./useChatStream";
import { ApprovalModal } from "./ApprovalModal";
import { ToolInputPanel } from "./ToolInputPanel";

export function ChatPage() {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    isStreaming,
    pendingApprovals,
    pendingClientTool,
    error,
    send,
    approve,
    deny,
    submitClientResult,
    clearError,
  } = useChatStream();

  // Get first pending approval (show one at a time)
  const currentApproval =
    pendingApprovals.size > 0
      ? pendingApprovals.values().next().value
      : null;

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isStreaming) return;

    const text = inputText;
    setInputText("");
    await send(text);
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
      {error && (
        <div className="max-w-4xl mx-auto w-full px-4 pt-4">
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={clearError}
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
                Ask questions about your log data. I'll help you analyze it
                with SQL.
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
            messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))
          )}

          {/* Tool input panel */}
          <ToolInputPanel
            clientTool={pendingClientTool}
            onComplete={submitClientResult}
            isLoading={isStreaming}
          />

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Input form */}
      <footer className="border-t bg-white px-4 py-3">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto flex gap-3"
        >
          <div className="flex-1">
            <Input
              value={inputText}
              onChange={(e) => setInputText(e.currentTarget.value)}
              placeholder="Type a message..."
              disabled={isStreaming || pendingApprovals.size > 0}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
            />
          </div>
          <Button
            type="submit"
            disabled={!inputText.trim() || pendingApprovals.size > 0 || isStreaming}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isStreaming && (
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

      {/* Approval modal */}
      <ApprovalModal
        approval={currentApproval ?? null}
        onApprove={approve}
        onDeny={deny}
        isLoading={isStreaming}
      />
    </div>
  );
}

/**
 * Message bubble component.
 */
function MessageBubble({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";
  const [datasetPreview, setDatasetPreview] = useState<{
    dataset: string;
    rows: Record<string, unknown>[];
    columns: string[];
    original_row_count: number;
    exported_row_count: number;
  } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Auto-preview the first Out[n] reference in assistant messages (if available).
  useEffect(() => {
    if (isUser) return;
    if (!message.content) return;
    if (datasetPreview || previewError) return;
    const match = message.content.match(/Out\\[\\d+\\]/);
    if (!match) return;
    const dataset = match[0];

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/data/${encodeURIComponent(dataset)}`);
        if (!res.ok) {
          throw new Error(`Failed to fetch data: ${res.statusText}`);
        }
        const data = await res.json();
        if (!cancelled) {
          setDatasetPreview({ dataset, ...data });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        if (!cancelled) setPreviewError(msg);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isUser, message.content, datasetPreview, previewError]);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-3 ${
          isUser
            ? "bg-gray-900 text-white"
            : "bg-white border border-gray-200 text-gray-800"
        }`}
      >
        <div className="text-sm whitespace-pre-wrap">
          {message.content || (
            <span className="text-gray-400 italic">Thinking...</span>
          )}
        </div>

        {!isUser && datasetPreview && (
          <div className="mt-3 bg-gray-50 border border-gray-200 rounded p-3 overflow-auto">
            <div className="text-xs text-gray-600 mb-2">
              {datasetPreview.dataset} プレビュー（{datasetPreview.exported_row_count} 行 /{" "}
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
                      <td key={c} className="pr-3 py-1 border-b border-gray-100">
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
