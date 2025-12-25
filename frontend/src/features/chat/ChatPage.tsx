/**
 * Main chat page component.
 */

import { useState, useRef, useEffect } from "react";
import { Input } from "baseui/input";
import { Button } from "baseui/button";
import { Notification, KIND } from "baseui/notification";
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
          <Notification
            kind={KIND.negative}
            onClose={clearError}
            closeable
          >
            {error}
          </Notification>
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
              clearable
              clearOnEscape
            />
          </div>
          <Button
            type="submit"
            isLoading={isStreaming}
            disabled={!inputText.trim() || pendingApprovals.size > 0}
          >
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
      </div>
    </div>
  );
}
