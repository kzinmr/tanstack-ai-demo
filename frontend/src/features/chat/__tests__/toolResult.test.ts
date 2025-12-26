import { describe, expect, it } from "vitest";
import { parseToolResult } from "../toolResult";

describe("parseToolResult", () => {
  it("parses valid JSON with artifacts", () => {
    const content = JSON.stringify({
      message: "Query executed",
      artifacts: [{ id: "a_abc12345_1", type: "table", row_count: 10 }],
    });
    const result = parseToolResult(content);
    expect(result?.artifacts?.[0].id).toBe("a_abc12345_1");
  });

  it("returns null for non-JSON content", () => {
    const result = parseToolResult("plain text response");
    expect(result).toBeNull();
  });

  it("handles missing artifacts field", () => {
    const content = JSON.stringify({ message: "Error occurred" });
    const result = parseToolResult(content);
    expect(result?.message).toBe("Error occurred");
    expect(result?.artifacts).toBeUndefined();
  });
});
