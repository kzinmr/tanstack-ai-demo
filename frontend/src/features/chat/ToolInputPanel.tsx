/**
 * Panel for client-side tool execution (e.g., CSV export).
 */

import { Button } from "baseui/button";
import { ClientToolInfo } from "./useChatStream";

interface ToolInputPanelProps {
  clientTool: ClientToolInfo | null;
  onComplete: (toolCallId: string, result: Record<string, unknown>) => void;
  isLoading: boolean;
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
  if (!clientTool) return null;

  const handleExecute = () => {
    const { rows, columns } = clientTool.input;

    if (!rows || !columns) {
      console.error("Missing rows or columns in tool input");
      onComplete(clientTool.toolCallId, {
        error: "Missing data",
        success: false,
      });
      return;
    }

    try {
      const result = downloadCSV(rows, columns, "export.csv");
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

  const rowCount = clientTool.input.rows?.length ?? 0;
  const columnCount = clientTool.input.columns?.length ?? 0;
  const originalCount = clientTool.input.original_row_count ?? rowCount;

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
