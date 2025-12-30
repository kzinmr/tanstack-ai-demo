export type ContinuationState = {
  pending: boolean;
  runId: string | null;
  approvals: Record<string, boolean>;
  toolResults: Record<string, unknown>;
};

export type ArtifactDataInline = {
  mode?: "inline";
  rows: Record<string, unknown>[];
  columns: string[];
  original_row_count: number;
  exported_row_count: number;
};

export type ArtifactDataSignedUrl = {
  mode: "signed-url";
  download_url: string;
  expires_in_seconds?: number;
  method?: string;
  headers?: Record<string, string>;
  columns?: string[];
  original_row_count?: number;
  exported_row_count?: number;
};

export type ArtifactData = ArtifactDataInline | ArtifactDataSignedUrl;

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
  runId?: string;
};
