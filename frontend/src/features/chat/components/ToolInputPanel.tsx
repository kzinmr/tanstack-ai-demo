/**
 * Panel for client-side tool execution (e.g., CSV export).
 */

import { useMemo, useState, useEffect } from "react";
import { Button } from "@base-ui/react/button";
import type { ArtifactData, ClientToolInfo, ToolResultPayload } from "../types";
import { fetchArtifactData } from "../services/dataService";
import { buildToolResultEnvelope } from "../utils/parsing";

interface ToolInputPanelProps {
  clientTool: ClientToolInfo | null;
  onComplete: (
    toolCallId: string,
    toolName: string,
    payload: ToolResultPayload
  ) => void;
  isLoading: boolean;
}

/**
 * Spinner component for loading states.
 */
function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

/**
 * Generate and download a CSV file from the provided data.
 */
function downloadCSV(
  rows: Record<string, unknown>[],
  columns: string[],
  filename: string = "result.csv"
): { filename: string; rowCount: number } {
  // Build CSV content
  const csvLines: string[] = [];

  // Header row
  csvLines.push(columns.map(escapeCSVValue).join(","));

  // Data rows
  for (const row of rows) {
    const values = columns.map((col) => {
      const value = row[col];
      return escapeCSVValue(value);
    });
    csvLines.push(values.join(","));
  }

  const csv = csvLines.join("\n");

  // Create and trigger download
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  return { filename, rowCount: rows.length };
}

function downloadSignedUrl(url: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.rel = "noopener";
  link.target = "_blank";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Escape a value for CSV format.
 */
function escapeCSVValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  const str = String(value);

  // If the value contains comma, newline, or quote, wrap in quotes
  if (str.includes(",") || str.includes("\n") || str.includes('"')) {
    return `"${str.replace(/"/g, '""')}"`;
  }

  return str;
}

export function ToolInputPanel({
  clientTool,
  onComplete,
  isLoading,
}: ToolInputPanelProps) {
  const [artifactData, setArtifactData] = useState<ArtifactData | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  const resolveArtifactId = (value: unknown): string | null => {
    if (!value || typeof value !== "object") return null;
    const obj = value as Record<string, unknown>;
    const direct =
      typeof obj.artifact_id === "string"
        ? obj.artifact_id
        : typeof obj.artifactId === "string"
          ? obj.artifactId
          : null;
    if (direct) return direct;
    const nested = obj.input;
    if (nested && typeof nested === "object") {
      const nestedObj = nested as Record<string, unknown>;
      if (typeof nestedObj.artifact_id === "string")
        return nestedObj.artifact_id;
      if (typeof nestedObj.artifactId === "string")
        return nestedObj.artifactId;
    }
    return null;
  };

  const artifactId = useMemo((): string | null => {
    if (!clientTool?.input) return null;
    const raw = clientTool.input as unknown;

    // Some backends may send the args as a JSON string.
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (!trimmed) return null;
      // JSON string { "artifact_id": "a_..." }
      try {
        const parsed = JSON.parse(trimmed) as unknown;
        const parsedId = resolveArtifactId(parsed);
        if (parsedId) return parsedId;
      } catch {
        // ignore
      }
      return trimmed;
    }

    return resolveArtifactId(raw);
  }, [clientTool?.input]);

  // Fetch CSV data when clientTool changes
  useEffect(() => {
    if (!artifactId) {
      setArtifactData(null);
      setFetchError(
        clientTool ? "Missing artifact reference in tool input" : null
      );
      return;
    }

    const fetchData = async () => {
      setIsFetching(true);
      setFetchError(null);
      try {
        const artifact = artifactId;
        const runId = clientTool?.runId;
        if (!runId) {
          throw new Error("Missing run ID for data fetch");
        }
        const data = await fetchArtifactData(runId, artifact, "download");
        setArtifactData(data);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setFetchError(message);
      } finally {
        setIsFetching(false);
      }
    };

    fetchData();
  }, [clientTool, artifactId]);

  if (!clientTool) return null;

  const handleExecute = () => {
    if (!artifactData) {
      const message = "No data available";
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: buildToolResultEnvelope("CSV download failed.", {
          data: { error: message, success: false },
        }),
        state: "output-error",
        errorText: message,
      });
      return;
    }

    try {
      if (artifactData.mode === "signed-url") {
        downloadSignedUrl(artifactData.download_url);
        onComplete(clientTool.toolCallId, clientTool.toolName, {
          output: buildToolResultEnvelope("CSV download started.", {
            data: { download_url: artifactData.download_url, success: true },
          }),
          state: "output-available",
        });
        return;
      }

      const result = downloadCSV(
        artifactData.rows,
        artifactData.columns,
        "export.csv"
      );
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: buildToolResultEnvelope("CSV download completed.", {
          data: { ...result, success: true },
        }),
        state: "output-available",
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: buildToolResultEnvelope("CSV download failed.", {
          data: { error: message, success: false },
        }),
        state: "output-error",
        errorText: message,
      });
    }
  };

  // Show loading state while fetching
  if (isFetching) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 my-4">
        <div className="flex items-center gap-3">
          <Spinner className="h-6 w-6 text-blue-500" />
          <span className="text-blue-700">Loading export data...</span>
        </div>
      </div>
    );
  }

  // Show error if fetch failed
  if (fetchError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 my-4">
        <p className="text-red-700">Error loading data: {fetchError}</p>
      </div>
    );
  }

  const isSignedUrl = artifactData?.mode === "signed-url";
  const inlineData =
    artifactData && artifactData.mode !== "signed-url" ? artifactData : null;
  const rowCount = inlineData?.exported_row_count ?? 0;
  const columnCount = inlineData?.columns?.length ?? 0;
  const originalCount = inlineData?.original_row_count ?? rowCount;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 my-4">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className="w-6 h-6 text-blue-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-blue-900">CSV Export Ready</h3>
          <p className="text-sm text-blue-700 mt-1">
            {isSignedUrl
              ? "Download will open using a signed URL."
              : `${rowCount} rows, ${columnCount} columns`}
            {!isSignedUrl && originalCount > rowCount && (
              <span className="text-blue-500">
                {" "}
                (limited from {originalCount} rows)
              </span>
            )}
          </p>
          <div className="mt-3">
            <Button
              onClick={handleExecute}
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isLoading && <Spinner className="h-4 w-4" />}
              Download CSV
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
