import { useMemo } from "react";
import type { UIMessage } from "@tanstack/ai";
import type { ApprovalInfo } from "../types";
import { extractArtifactId } from "../utils/parsing";
import { ArtifactPreview } from "./ArtifactPreview";
import { MessagePartView } from "./MessagePartView";

interface MessageBubbleProps {
  message: UIMessage;
  runId?: string;
  pendingApprovalByToolCallId: Record<string, ApprovalInfo>;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
  showInlineApprovalActions?: boolean;
}

export function MessageBubble({
  message,
  runId,
  pendingApprovalByToolCallId,
  onApprove,
  onDeny,
  isLoading,
  showInlineApprovalActions,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const artifactId = useMemo(
    () => extractArtifactId(message.parts),
    [message.parts]
  );

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
                showInlineApprovalActions={showInlineApprovalActions}
              />
            ))
          )}
        </div>

        {!isUser && (
          <ArtifactPreview runId={runId} artifactId={artifactId || undefined} />
        )}
      </div>
    </div>
  );
}
