import { fetchServerSentEvents, type ConnectionAdapter } from "@tanstack/ai-react";

export function createChatConnection(
  getRunId: () => string | null,
  apiBase = ""
): ConnectionAdapter {
  return fetchServerSentEvents(`${apiBase}/api/chat`, async () => {
    const runId = getRunId();
    return {
      headers: { Accept: "text/event-stream" },
      body: runId ? { run_id: runId } : undefined,
    };
  });
}
