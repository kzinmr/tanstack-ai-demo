/**
 * Sticky panel for tool approval requests.
 */

import { Button } from "@base-ui/react/button";
import type { ApprovalInfo } from "../types";

interface PendingApprovalsPanelProps {
  approvals: ApprovalInfo[];
  onApprove: (approvalId: string) => void;
  onDeny: (approvalId: string) => void;
  isLoading: boolean;
  isProcessing?: boolean;
}

function formatInput(input: unknown): string {
  if (typeof input === "string") return input;
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

export function PendingApprovalsPanel({
  approvals,
  onApprove,
  onDeny,
  isLoading,
  isProcessing = false,
}: PendingApprovalsPanelProps) {
  if (approvals.length === 0) return null;

  const current = approvals[0];
  const remaining = approvals.length - 1;

  return (
    <div className="border-t-4 border-amber-400 bg-amber-50 px-4 py-3 shadow-sm">
      <div className="max-w-4xl mx-auto flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-amber-700">
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </span>
            <h3 className="text-sm font-semibold text-amber-900">
              {isProcessing ? "Approval submitted" : "Approval required"}
            </h3>
            {remaining > 0 && (
              <span className="text-xs text-amber-700">
                +{remaining} more pending
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-amber-800">
            {isProcessing
              ? `Running tool ${current.toolName}...`
              : `Tool ${current.toolName} wants to run. Review the input and approve or deny.`}
          </p>
          <pre className="mt-2 rounded border border-amber-200 bg-white/70 p-3 text-xs font-mono text-gray-800 max-h-40 overflow-auto whitespace-pre-wrap shadow-inner">
            {formatInput(current.input)}
          </pre>
        </div>

        <div className="flex gap-2 sm:pt-2">
          {isProcessing ? (
            <div className="flex items-center gap-2 text-sm text-amber-800">
              <span className="inline-flex h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              Processing approval...
            </div>
          ) : (
            <>
              <Button
                onClick={() => onDeny(current.id)}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-amber-900 bg-white border border-amber-200 rounded-md hover:bg-amber-100 shadow-sm transition-colors"
              >
                Deny
              </Button>
              <Button
                onClick={() => onApprove(current.id)}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700 shadow-sm transition-colors flex items-center gap-2"
              >
                {isLoading && <span className="animate-pulse">...</span>}
                Approve
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
