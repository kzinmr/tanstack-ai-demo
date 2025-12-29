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
