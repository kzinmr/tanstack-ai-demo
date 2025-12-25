/**
 * Modal for approving/denying tool execution requests.
 */

import { Dialog } from "@base-ui/react/dialog";
import { Button } from "@base-ui/react/button";
import { ApprovalInfo } from "./useChatStream";

interface ApprovalModalProps {
  approval: ApprovalInfo | null;
  onApprove: (toolCallId: string) => void;
  onDeny: (toolCallId: string) => void;
  isLoading: boolean;
}

export function ApprovalModal({
  approval,
  onApprove,
  onDeny,
  isLoading,
}: ApprovalModalProps) {
  if (!approval) return null;

  const formatInput = (input: unknown): string => {
    if (typeof input === "string") return input;
    try {
      return JSON.stringify(input, null, 2);
    } catch {
      return String(input);
    }
  };

  return (
    <Dialog.Root open={!!approval} onOpenChange={(open) => !open && onDeny(approval.toolCallId)}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 bg-black/50 z-40" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl z-50 w-full max-w-lg max-h-[90vh] overflow-hidden">
          <Dialog.Title className="text-lg font-semibold px-6 py-4 border-b">
            Approval Required
          </Dialog.Title>
          <div className="px-6 py-4 space-y-4 overflow-auto max-h-[60vh]">
            <div>
              <p className="text-sm text-gray-500 mb-1">Tool:</p>
              <p className="font-medium">{approval.toolName}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-1">Input:</p>
              <pre className="bg-gray-100 p-3 rounded text-sm overflow-auto max-h-64">
                {formatInput(approval.input)}
              </pre>
            </div>
            <p className="text-sm text-gray-600">
              Do you want to allow this tool to execute?
            </p>
          </div>
          <div className="px-6 py-4 border-t flex justify-end gap-3">
            <Button
              onClick={() => onDeny(approval.toolCallId)}
              disabled={isLoading}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Deny
            </Button>
            <Button
              onClick={() => onApprove(approval.toolCallId)}
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
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
              Approve
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
