/**
 * Panel for client-side tool execution (e.g., CSV export).
 */

import { useMemo, useState, useEffect } from "react";
import { Button } from "@base-ui/react/button";

export interface ClientToolInfo {
  toolCallId: string;
  toolName: string;
  input: unknown;
  runId: string;
}

export interface ToolResultPayload {
  output: Record<string, unknown>;
  state?: "output-available" | "output-error";
  errorText?: string;
}

interface ToolInputPanelProps {
  clientTool: ClientToolInfo | null;
  onComplete: (
    toolCallId: string,
    toolName: string,
    payload: ToolResultPayload
  ) => void;
  isLoading: boolean;
}

interface CSVData {
  rows: Record<string, unknown>[];
  columns: string[];
  original_row_count: number;
  exported_row_count: number;
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
  const [csvData, setCsvData] = useState<CSVData | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  const datasetRef = useMemo((): string | null => {
    if (!clientTool?.input) return null;
    const raw = clientTool.input as unknown;

    // Some backends may send the args as a JSON string.
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      // Raw Out[n]
      if (/^Out\[\d+\]$/.test(trimmed)) return trimmed;
      // JSON string { "dataset": "Out[1]" }
      try {
        const parsed = JSON.parse(trimmed) as any;
        if (parsed && typeof parsed.dataset === "string") return parsed.dataset;
      } catch {
        // ignore
      }
      return null;
    }

    if (typeof raw === "object" && raw !== null) {
      const obj: any = raw;
      if (typeof obj.dataset === "string") return obj.dataset;
      // In case nested shapes appear, try common fallbacks.
      if (obj.input && typeof obj.input.dataset === "string")
        return obj.input.dataset;
    }

    return null;
  }, [clientTool?.toolCallId, clientTool?.input]);

  // Fetch CSV data when clientTool changes
  useEffect(() => {
    if (!datasetRef) {
      setCsvData(null);
      setFetchError(
        clientTool ? "Missing dataset reference in tool input" : null
      );
      return;
    }

    const fetchData = async () => {
      setIsFetching(true);
      setFetchError(null);
      try {
        const dataset = datasetRef;
        const runId = clientTool?.runId;
        if (!runId) {
          throw new Error("Missing run ID for data fetch");
        }
        const response = await fetch(
          `/api/data/${encodeURIComponent(runId)}/${encodeURIComponent(dataset!)}`
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch data: ${response.statusText}`);
        }
        const data = await response.json();
        setCsvData(data);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown error";
        setFetchError(message);
      } finally {
        setIsFetching(false);
      }
    };

    fetchData();
  }, [clientTool?.toolCallId, clientTool?.runId, datasetRef]);

  if (!clientTool) return null;

  const handleExecute = () => {
    if (!csvData) {
      const message = "No data available";
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: { error: message, success: false },
        state: "output-error",
        errorText: message,
      });
      return;
    }

    try {
      const result = downloadCSV(csvData.rows, csvData.columns, "export.csv");
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: { ...result, success: true },
        state: "output-available",
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      onComplete(clientTool.toolCallId, clientTool.toolName, {
        output: { error: message, success: false },
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
          <span className="text-blue-700">Loading CSV data...</span>
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

  const rowCount = csvData?.exported_row_count ?? 0;
  const columnCount = csvData?.columns?.length ?? 0;
  const originalCount = csvData?.original_row_count ?? rowCount;

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
            {rowCount} rows, {columnCount} columns
            {originalCount > rowCount && (
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
