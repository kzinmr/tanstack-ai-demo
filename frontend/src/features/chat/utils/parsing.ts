import type { MessagePart } from "@tanstack/ai";

export const TOOL_RESULT_ENVELOPE_VERSION = 1;

export type ToolResultEnvelope = {
  type: "tool_result";
  version: number;
  message?: string;
  artifacts?: Array<{
    id: string;
    type?: string;
    row_count?: number;
  }>;
  data?: Record<string, unknown>;
};

export type ParsedToolResult = ToolResultEnvelope;

export function parseToolArguments(argumentsText: string): unknown {
  if (!argumentsText) return {};
  try {
    return JSON.parse(argumentsText);
  } catch {
    return argumentsText;
  }
}

export function formatToolArguments(argumentsText: string): string {
  if (!argumentsText) return "{}";
  try {
    return JSON.stringify(JSON.parse(argumentsText), null, 2);
  } catch {
    return argumentsText;
  }
}

export function parseToolResult(content: string): ParsedToolResult | null {
  if (!content) return null;
  try {
    const parsed = JSON.parse(content);
    if (!parsed || typeof parsed !== "object") return null;
    const payload = parsed as Record<string, unknown>;
    if (payload.type !== "tool_result") return null;
    if (payload.version !== TOOL_RESULT_ENVELOPE_VERSION) return null;

    const message =
      typeof payload.message === "string" ? payload.message : undefined;
    const artifacts = Array.isArray(payload.artifacts)
      ? payload.artifacts
          .map((item) => {
            if (!item || typeof item !== "object") return null;
            const obj = item as Record<string, unknown>;
            if (typeof obj.id !== "string") return null;
            const type = typeof obj.type === "string" ? obj.type : undefined;
            const row_count =
              typeof obj.row_count === "number" ? obj.row_count : undefined;
            return { id: obj.id, type, row_count };
          })
          .filter((item): item is NonNullable<typeof item> => item !== null)
      : undefined;
    const data =
      payload.data && typeof payload.data === "object" && !Array.isArray(payload.data)
        ? (payload.data as Record<string, unknown>)
        : undefined;

    if (!message && (!artifacts || artifacts.length === 0) && !data) {
      return null;
    }

    return {
      type: "tool_result",
      version: TOOL_RESULT_ENVELOPE_VERSION,
      message,
      artifacts,
      data,
    };
  } catch {
    return null;
  }
}

export function buildToolResultEnvelope(
  message: string,
  options?: {
    artifacts?: ToolResultEnvelope["artifacts"];
    data?: ToolResultEnvelope["data"];
  }
): ToolResultEnvelope {
  return {
    type: "tool_result",
    version: TOOL_RESULT_ENVELOPE_VERSION,
    message,
    artifacts: options?.artifacts,
    data: options?.data,
  };
}

export function extractArtifactId(parts: MessagePart[]): string | null {
  for (const part of parts) {
    if (part.type !== "tool-result") continue;
    const payload = parseToolResult(part.content);
    if (payload?.artifacts?.length) {
      return payload.artifacts[0].id;
    }
  }
  return null;
}

export function extractArtifacts(parts: MessagePart[]): Array<{ id: string; type?: string }> {
  const seen = new Set<string>();
  const results: Array<{ id: string; type?: string }> = [];
  for (const part of parts) {
    if (part.type !== "tool-result") continue;
    const payload = parseToolResult(part.content);
    if (!payload?.artifacts) continue;
    for (const artifact of payload.artifacts) {
      if (seen.has(artifact.id)) continue;
      seen.add(artifact.id);
      results.push({ id: artifact.id, type: artifact.type });
    }
  }
  return results;
}
