import { useMemo, useState } from "react";
import type { ToolResultPart } from "@tanstack/ai";
import { parseToolResult } from "../utils/parsing";

interface ToolResultPartViewProps {
  part: ToolResultPart;
}

export function ToolResultPartView({ part }: ToolResultPartViewProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const parsed = useMemo(() => parseToolResult(part.content), [part.content]);
  const displayText = parsed?.message ?? part.content;
  const label = parsed ? "Tool result" : "Raw tool result";

  return (
    <div className="rounded-md border border-gray-200 bg-white p-2 text-xs">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1 text-gray-500 hover:text-gray-700 w-full text-left"
      >
        <svg
          className={`w-3 h-3 transition-transform ${isExpanded ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span>{label}</span>
      </button>
      {isExpanded && (
        <div className="whitespace-pre-wrap text-gray-700 mt-2 pl-4">
          {displayText}
        </div>
      )}
    </div>
  );
}
