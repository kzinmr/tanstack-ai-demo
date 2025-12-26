import { useState } from "react";
import type { ToolCallPart } from "@tanstack/ai";
import { ApprovalCard } from "./ApprovalCard";
import type { ApprovalInfo } from "../types";
import { formatToolArguments, parseToolArguments } from "../utils/parsing";

interface ToolCallPartViewProps {
  part: ToolCallPart;
  pendingApproval?: ApprovalInfo;
  onApprove?: (approvalId: string) => void;
  onDeny?: (approvalId: string) => void;
  isLoading?: boolean;
}

export function ToolCallPartView({
  part,
  pendingApproval,
  onApprove,
  onDeny,
  isLoading = false,
}: ToolCallPartViewProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const approvalStatus = part.approval?.approved;
  const needsApproval = part.approval?.needsApproval ?? false;
  const isPendingApproval =
    (needsApproval && approvalStatus === undefined) || !!pendingApproval;
  const approvalId = pendingApproval?.id ?? part.approval?.id;
  const approvalInput =
    pendingApproval?.input ?? parseToolArguments(part.arguments);
  const hasApprovalRequest = needsApproval || !!pendingApproval;

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
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center justify-between w-full text-left"
        >
          <div className="flex items-center gap-1">
            <svg
              className={`w-3 h-3 text-gray-500 transition-transform ${isExpanded ? "rotate-90" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
            <span className="font-medium text-gray-700">
              Tool: {part.name}
            </span>
          </div>
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
        </button>
        {isExpanded && (
          <pre className="mt-2 whitespace-pre-wrap text-gray-600 pl-4">
            {formatToolArguments(part.arguments)}
          </pre>
        )}
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
