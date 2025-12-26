import type { ArtifactData } from "../types";

export async function fetchArtifactData(
  runId: string,
  artifactId: string
): Promise<ArtifactData> {
  const response = await fetch(
    `/api/data/${encodeURIComponent(runId)}/${encodeURIComponent(artifactId)}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch data: ${response.statusText}`);
  }
  return (await response.json()) as ArtifactData;
}
