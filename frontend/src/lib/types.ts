/* Domain types mirroring the backend response shapes. */

export type VarKind = "id" | "binary" | "categorical" | "numeric" | "string";
export type SparklineKind = "binary" | "categorical" | "numeric" | "flat";

export interface ColumnInfo {
  name: string;
  dtype: string;
  stata_type: string | null;
  label: string;
  kind: VarKind;
  n: number;
  n_missing: number;
  missing_pct: number;
  n_unique: number;
  value_labels: Record<string, string>;
  sparkline: number[];
  sparkline_kind: SparklineKind;
}

export interface Dataset {
  filename: string;
  n_obs: number;
  n_vars: number;
  columns: string[];
}

export interface UploadResponse extends Dataset {
  frame: string;
  storage_types: Record<string, string>;
  column_labels: Record<string, string>;
  preview: Array<Record<string, unknown>>;
}

export interface ColumnsResponse {
  frame: string;
  columns: ColumnInfo[];
}

export interface HistogramResponse {
  variable: string;
  kind: SparklineKind;
  bins: number[];
  edges: number[] | null;
  labels: string[] | null;
  n: number;
  n_missing: number;
  min: number | null;
  max: number | null;
  mean: number | null;
}

export interface SummarizeRow {
  Variable: string;
  Obs: number;
  Mean?: number | null;
  SD?: number | null;
  Min?: number | null;
  Max?: number | null;
  // detail-only fields
  Variance?: number | null;
  Skewness?: number | null;
  Kurtosis?: number | null;
  p1?: number; p5?: number; p10?: number; p25?: number;
  p50?: number; p75?: number; p90?: number; p95?: number; p99?: number;
}

export interface SummarizeResult {
  command: string;
  result: { variables: SummarizeRow[]; detail: boolean };
  text: string;
  r_set: Record<string, number | null>;
  e_set: Record<string, unknown> | null;
}

export type Mode = "guided" | "pro";
export type Step = "import" | "inspect" | "clean" | "analyze" | "visualize" | "export";
