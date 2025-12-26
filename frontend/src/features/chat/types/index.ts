export type ContinuationState = {
  pending: boolean;
  runId: string | null;
  approvals: Record<string, boolean>;
  toolResults: Record<string, unknown>;
};

export interface ArtifactData {
  rows: Record<string, unknown>[];
  columns: string[];
  original_row_count: number;
  exported_row_count: number;
}

export type ClientToolInfo = {
  toolCallId: string;
  toolName: string;
  input: unknown;
  runId: string;
};

export type ToolResultPayload = {
  output: Record<string, unknown>;
  state?: "output-available" | "output-error";
  errorText?: string;
};

export type ApprovalInfo = {
  id: string;
  toolCallId: string;
  toolName: string;
  input: unknown;
};
