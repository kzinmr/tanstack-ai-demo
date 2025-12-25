/**
 * Panel for client-side tool execution (e.g., CSV export).
 */

import { useState, useEffect } from "react";
import { Button } from "baseui/button";
import { Spinner } from "baseui/spinner";
import { ClientToolInfo } from "./useChatStream";

interface ToolInputPanelProps {
  clientTool: ClientToolInfo | null;
  onComplete: (toolCallId: string, result: Record<string, unknown>) => void;
  isLoading: boolean;
}

interface CSVData {
  rows: Record<string, unknown>[];
  columns: string[];
  original_row_count: number;
  exported_row_count: number;
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

  // Fetch CSV data when clientTool changes
  useEffect(() => {
    if (!clientTool?.input.dataset) {
      setCsvData(null);
      setFetchError(null);
      return;
    }

    const fetchData = async () => {
      setIsFetching(true);
      setFetchError(null);
      try {
        const dataset = clientTool.input.dataset;
        const response = await fetch(`/api/data/${encodeURIComponent(dataset!)}`);
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
  }, [clientTool?.toolCallId, clientTool?.input.dataset]);

  if (!clientTool) return null;

  const handleExecute = () => {
    if (!csvData) {
      onComplete(clientTool.toolCallId, {
        error: "No data available",
        success: false,
      });
      return;
    }

    try {
      const result = downloadCSV(csvData.rows, csvData.columns, "export.csv");
      onComplete(clientTool.toolCallId, {
        ...result,
        success: true,
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      onComplete(clientTool.toolCallId, {
        error: message,
        success: false,
      });
    }
  };

  // Show loading state while fetching
  if (isFetching) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 my-4">
        <div className="flex items-center gap-3">
          <Spinner size={24} />
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
              isLoading={isLoading}
              size="compact"
            >
              Download CSV
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
