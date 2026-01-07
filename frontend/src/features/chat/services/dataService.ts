import type { ArtifactData } from "../types";

export async function fetchArtifactData(
  runId: string,
  artifactId: string,
  mode: "preview" | "download" = "preview"
): Promise<ArtifactData> {
  const query = mode ? `?mode=${encodeURIComponent(mode)}` : "";
  const response = await fetch(
    `/api/data/${encodeURIComponent(runId)}/${encodeURIComponent(artifactId)}${query}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch data: ${response.statusText}`);
  }
  return (await response.json()) as ArtifactData;
}

export async function postContinuation(
  runId: string,
  payload: {
    approvals?: Record<string, boolean | Record<string, unknown>>;
    toolResults?: Record<string, unknown>;
  }
): Promise<void> {
  const response = await fetch("/api/continuation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      approvals: payload.approvals ?? {},
      tool_results: payload.toolResults ?? {},
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to continue run: ${response.statusText}`);
  }
}
