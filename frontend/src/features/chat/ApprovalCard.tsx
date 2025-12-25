/**
 * Inline approval card component for tool execution requests.
 * Displayed within the chat panel instead of a modal.
 */

import { Button } from "@base-ui/react/button";

/**
 * Information about a pending approval request.
 */
export interface ApprovalInfo {
  id: string;
  toolCallId: string;
  toolName: string;
  input: unknown;
}

export interface ApprovalCardProps {
  approvalId: string;
  toolName: string;
  input: unknown;
  onApprove: (approvalId: string) => void;
  onDeny: (approvalId: string) => void;
  isLoading: boolean;
}

function formatInput(input: unknown): string {
  if (typeof input === "string") return input;
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

export function ApprovalCard({
  approvalId,
  toolName,
  input,
  onApprove,
  onDeny,
  isLoading,
}: ApprovalCardProps) {
  return (
    <div className="mt-2 border-2 border-amber-200 bg-amber-50 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-amber-600 text-sm font-medium">
          Approval Required
        </span>
        <span className="text-xs text-gray-500">Tool: {toolName}</span>
      </div>

      <div className="mb-3">
        <pre className="bg-white border border-amber-100 p-2 rounded text-xs overflow-auto max-h-32">
          {formatInput(input)}
        </pre>
      </div>

      <div className="flex gap-2">
        <Button
          onClick={() => onDeny(approvalId)}
          disabled={isLoading}
          className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Deny
        </Button>
        <Button
          onClick={() => onApprove(approvalId)}
          disabled={isLoading}
          className="px-3 py-1.5 text-sm bg-amber-500 text-white rounded-md hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-1 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-1"
        >
          {isLoading && (
            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
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
          Approve
        </Button>
      </div>
    </div>
  );
}
