/**
 * Modal for approving/denying tool execution requests.
 */

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalButton,
} from "baseui/modal";
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
    <Modal
      isOpen={!!approval}
      onClose={() => onDeny(approval.toolCallId)}
      closeable={!isLoading}
    >
      <ModalHeader>Approval Required</ModalHeader>
      <ModalBody>
        <div className="space-y-4">
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
      </ModalBody>
      <ModalFooter>
        <ModalButton
          kind="tertiary"
          onClick={() => onDeny(approval.toolCallId)}
          disabled={isLoading}
        >
          Deny
        </ModalButton>
        <ModalButton
          onClick={() => onApprove(approval.toolCallId)}
          isLoading={isLoading}
        >
          Approve
        </ModalButton>
      </ModalFooter>
    </Modal>
  );
}
