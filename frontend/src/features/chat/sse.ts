/**
 * SSE (Server-Sent Events) parser for TanStack AI protocol.
 *
 * Parses SSE frames and yields JSON chunks.
 * Terminates when [DONE] is received.
 */

/**
 * Parse SSE response and yield JSON chunks.
 *
 * @param response - Fetch response with SSE body
 * @yields Parsed JSON objects from each SSE data frame
 */
export async function* sseJsonIterator(
  response: Response
): AsyncGenerator<unknown> {
  if (!response.body) return;

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) buffer += decoder.decode(value, { stream: true });

      // Process complete SSE frames (separated by \n\n)
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        // Process each line in the frame
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);

          // Check for end of stream
          if (data === "[DONE]") return;

          // Parse and yield JSON
          try {
            yield JSON.parse(data);
          } catch (e) {
            console.error("Failed to parse SSE data:", data, e);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Stream chunk types from TanStack AI protocol.
 */
export type StreamChunkType =
  | "content"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "tool-input-available"
  | "approval-requested"
  | "error"
  | "done";

/**
 * Base structure for all stream chunks.
 */
export interface BaseStreamChunk {
  id: string;
  model: string;
  timestamp: number;
  type: StreamChunkType;
}

/**
 * Content chunk for text streaming.
 */
export interface ContentStreamChunk extends BaseStreamChunk {
  type: "content";
  content: string;
  delta: string;
  role?: "assistant";
}

/**
 * Tool call chunk.
 */
export interface ToolCallStreamChunk extends BaseStreamChunk {
  type: "tool_call";
  index: number;
  toolCall: {
    id: string;
    type: "function";
    function: {
      name: string;
      arguments: string;
    };
  };
}

/**
 * Tool result chunk.
 */
export interface ToolResultStreamChunk extends BaseStreamChunk {
  type: "tool_result";
  toolCallId: string;
  content: string;
}

/**
 * Approval requested chunk (HITL).
 */
export interface ApprovalRequestedStreamChunk extends BaseStreamChunk {
  type: "approval-requested";
  toolCallId: string;
  toolName: string;
  input: unknown;
  approval: {
    id: string;
    needsApproval: true;
  };
}

/**
 * Tool input available chunk (client-side execution).
 */
export interface ToolInputAvailableStreamChunk extends BaseStreamChunk {
  type: "tool-input-available";
  toolCallId: string;
  toolName: string;
  input: unknown;
}

/**
 * Error chunk.
 */
export interface ErrorStreamChunk extends BaseStreamChunk {
  type: "error";
  error: {
    message: string;
    code?: string;
  };
}

/**
 * Done chunk.
 */
export interface DoneStreamChunk extends BaseStreamChunk {
  type: "done";
  finishReason: "stop" | "length" | "tool_calls" | "content_filter";
  usage?: {
    completionTokens: number;
    promptTokens: number;
    totalTokens: number;
  };
}

/**
 * Union of all stream chunk types.
 */
export type StreamChunk =
  | ContentStreamChunk
  | ToolCallStreamChunk
  | ToolResultStreamChunk
  | ApprovalRequestedStreamChunk
  | ToolInputAvailableStreamChunk
  | ErrorStreamChunk
  | DoneStreamChunk;
