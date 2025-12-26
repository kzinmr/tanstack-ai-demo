export type ParsedToolResult = {
  message?: string;
  artifacts?: Array<{
    id: string;
    type?: string;
    row_count?: number;
  }>;
};

export function parseToolResult(content: string): ParsedToolResult | null {
  if (!content) return null;
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object") return null;

    const message =
      typeof parsed.message === "string" ? parsed.message : undefined;
    const artifacts = Array.isArray(parsed.artifacts)
      ? parsed.artifacts
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

    if (!message && (!artifacts || artifacts.length === 0)) {
      return null;
    }

    return { message, artifacts };
  } catch {
    return null;
  }
}
