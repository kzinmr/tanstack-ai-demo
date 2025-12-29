/**
 * Main chat page component.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Input } from "@base-ui/react/input";
import { Button } from "@base-ui/react/button";
import { MessageBubble } from "./components/MessageBubble";
import { PendingApprovalsPanel } from "./components/PendingApprovalsPanel";
import { ToolInputPanel } from "./components/ToolInputPanel";
import { useChatSession } from "./hooks/useChatSession";
import type { ApprovalInfo } from "./types";

export function ChatPage() {
  const {
    messages,
    inputText,
    setInputText,
    submitMessage,
    isLoading,
    error,
    pendingClientTool,
    pendingApprovals,
    pendingApprovalByToolCallId,
    approve,
    deny,
    resolveClientTool,
    getRunIdForMessage,
  } = useChatSession();

  const [visibleError, setVisibleError] = useState<Error | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [lastApproval, setLastApproval] = useState<ApprovalInfo | null>(null);
  const hasPendingApprovals = pendingApprovals.length > 0;
  const currentApproval = useMemo(
    () => pendingApprovals[0] ?? null,
    [pendingApprovals]
  );
  const approvalsForPanel = useMemo(() => {
    if (hasPendingApprovals) return pendingApprovals;
    if (isLoading && lastApproval) return [lastApproval];
    return [];
  }, [hasPendingApprovals, pendingApprovals, isLoading, lastApproval]);
  const isProcessingApproval =
    !hasPendingApprovals && !!lastApproval && isLoading;

  useEffect(() => {
    setVisibleError(error ?? null);
  }, [error]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pendingClientTool, currentApproval]);

  useEffect(() => {
    if (hasPendingApprovals) {
      setLastApproval(pendingApprovals[0] ?? null);
      return;
    }
    if (!isLoading) {
      setLastApproval(null);
    }
  }, [hasPendingApprovals, pendingApprovals, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const text = inputText;
    setInputText("");
    await submitMessage(text);
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
                  "`records` から 2025-12-24 の error を集計したい。SQL
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
                runId={getRunIdForMessage(message.id)}
                pendingApprovalByToolCallId={pendingApprovalByToolCallId}
                onApprove={approve}
                onDeny={deny}
                isLoading={isLoading}
                showInlineApprovalActions={!hasPendingApprovals}
              />
            ))
          )}

          {/* Tool input panel */}
          <ToolInputPanel
            clientTool={pendingClientTool}
            onComplete={resolveClientTool}
            isLoading={isLoading}
          />

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </main>

      <div className="bg-gray-50/95 backdrop-blur-sm">
        <PendingApprovalsPanel
          approvals={approvalsForPanel}
          onApprove={approve}
          onDeny={deny}
          isLoading={isLoading}
          isProcessing={isProcessingApproval}
        />
        {/* Input form */}
        <footer className="border-t bg-white px-4 py-3">
          <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-3">
            <div className="flex-1">
              <Input
                value={inputText}
                onChange={(e) => setInputText(e.currentTarget.value)}
                placeholder="Type a message..."
                disabled={isLoading || hasPendingApprovals}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
              />
            </div>
            <Button
              type="submit"
              disabled={!inputText.trim() || hasPendingApprovals || isLoading}
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
    </div>
  );
}
