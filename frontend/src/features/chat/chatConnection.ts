import { fetchServerSentEvents, type ConnectionAdapter } from "@tanstack/ai-react";

type ContinuationState = {
  pending: boolean;
  runId: string | null;
  approvals: Record<string, boolean>;
  toolResults: Record<string, unknown>;
};

export function createChatConnection(
  getContinuationState: () => ContinuationState,
  apiBase = ""
): ConnectionAdapter {
  return fetchServerSentEvents(`${apiBase}/api/chat`, async () => {
    const { pending, runId, approvals, toolResults } = getContinuationState();
    const hasApprovals = Object.keys(approvals).length > 0;
    const hasToolResults = Object.keys(toolResults).length > 0;
    const isContinuation = pending && !!runId && (hasApprovals || hasToolResults);

    if (isContinuation) {
      return {
        headers: { Accept: "text/event-stream" },
        body: {
          run_id: runId,
          approvals,
          tool_results: toolResults,
        },
      };
    }

    return {
      headers: { Accept: "text/event-stream" },
    };
  });
}
