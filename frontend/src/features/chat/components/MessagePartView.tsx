import type { MessagePart } from "@tanstack/ai";
import type { ApprovalInfo } from "../types";
import { ToolCallPartView } from "./ToolCallPartView";
import { ToolResultPartView } from "./ToolResultPartView";

interface MessagePartViewProps {
  part: MessagePart;
  pendingApprovalByToolCallId: Record<string, ApprovalInfo>;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
}

export function MessagePartView({
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
