import type {
  InternalToolCallState,
  MessagePart,
  ToolCallPart,
  ToolResultPart,
  UIMessage,
} from "@tanstack/ai";
import { StreamProcessor } from "@tanstack/ai";

let patched = false;

export function applyTanstackCompat(): void {
  if (patched) return;
  patched = true;

  // Preserve approval state: avoid marking approval-required tool calls as input-complete
  // during stream finalization, otherwise auto-continue cannot find the approval.
  const prototype = StreamProcessor.prototype as unknown as {
    completeToolCall?: (index: number, toolCall: InternalToolCallState) => void;
  };

  const originalCompleteToolCall = prototype.completeToolCall;
  if (typeof originalCompleteToolCall === "function") {
    prototype.completeToolCall = function (
      this: StreamProcessor,
      index: number,
      toolCall: InternalToolCallState
    ): void {
      const processor = this as unknown as {
        messages?: UIMessage[];
        currentAssistantMessageId?: string | null;
      };
      const toolCallId = toolCall?.id;
      if (toolCallId && processor.currentAssistantMessageId && Array.isArray(processor.messages)) {
        const message = processor.messages.find(
          (entry) => entry.id === processor.currentAssistantMessageId
        );
        const part = message?.parts.find(
          (entry): entry is ToolCallPart => entry.type === "tool-call" && entry.id === toolCallId
        );
        if (part?.approval?.needsApproval && part.approval.approved === undefined) {
          return;
        }
      }
      originalCompleteToolCall.call(this, index, toolCall);
    };
  }

  // Treat tool-result parts as completion for auto-continue decisions.
  StreamProcessor.prototype.areAllToolsComplete = function (this: StreamProcessor): boolean {
    const messages: UIMessage[] = this.getMessages() ?? [];
    const lastAssistant = [...messages].reverse().find((message: UIMessage) => message.role === "assistant");
    if (!lastAssistant) return true;
    const toolCalls = lastAssistant.parts.filter(
      (part: MessagePart): part is ToolCallPart => part.type === "tool-call"
    );
    if (toolCalls.length === 0) return true;
    const toolResultIds = new Set(
      lastAssistant.parts
        .filter((part: MessagePart): part is ToolResultPart => part.type === "tool-result")
        .map((part: ToolResultPart) => part.toolCallId)
    );
    return toolCalls.every(
      (part: ToolCallPart) =>
        part.state === "approval-responded" ||
        ((part.output !== undefined || toolResultIds.has(part.id)) && !part.approval)
    );
  };

}
