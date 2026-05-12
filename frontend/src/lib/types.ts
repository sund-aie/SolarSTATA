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

export interface StagedSheet {
  name: string;
  n_rows: number;
  n_cols: number;
  preview_rows: string[][];   // raw, untyped first 10 rows
}

export interface StagedUploadResponse {
  requires_choice: true;
  file_id: string;
  format: "xlsx";
  original_filename: string;
  sheets: StagedSheet[];
}

export type UploadOrChoice = UploadResponse | StagedUploadResponse;

export const isStagedResponse = (r: UploadOrChoice): r is StagedUploadResponse =>
  (r as StagedUploadResponse).requires_choice === true;

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

export interface TabulateRow {
  value: string | number | boolean | null;
  freq: number;
  percent: number;
  cum: number;
}

export interface TabulateResult {
  command: string;
  result: {
    variable: string;
    n: number;
    n_categories: number;
    rows: TabulateRow[];
  };
  text: string;
  r_set: Record<string, number | null>;
  e_set: Record<string, unknown> | null;
}

export type Mode = "guided" | "pro";
export type Step = "import" | "inspect" | "clean" | "analyze" | "visualize" | "export";

// ===================================================================
// Regression family
// ===================================================================

export interface CoefRow {
  name: string;
  coef: number | null;
  se: number | null;
  t?: number | null;
  z?: number | null;
  p: number | null;
  ci_low: number | null;
  ci_high: number | null;
  significant: boolean;
  raw_coef?: number | null;     // logit: original-scale coef when displaying ORs
  raw_se?: number | null;
}

export interface RegressHeader {
  N: number;
  df_m: number;
  df_r: number;
  F: number | null;
  Prob_F: number | null;
  R2: number | null;
  R2_adj: number | null;
  RMSE: number | null;
  vce: string;
  cluster: string | null;
}

export interface LogitHeader {
  N: number;
  df_m: number;
  LR_chi2: number | null;
  Prob_chi2: number | null;
  Pseudo_R2: number | null;
  log_likelihood: number | null;
  log_likelihood_null: number | null;
  vce: string;
  cluster: string | null;
  odds_ratios: boolean;
}

export interface RegressResponse {
  command: string;
  result: {
    command: string;
    kind: "regress";
    depvar: string;
    indepvars: string[];
    header: RegressHeader;
    coefficients: CoefRow[];
    design_columns: string[];
  };
  text: string;
  r_set: Record<string, unknown>;
  e_set: Record<string, unknown> | null;
}

export interface LogitResponse {
  command: string;
  result: {
    command: string;
    kind: "logit";
    depvar: string;
    indepvars: string[];
    header: LogitHeader;
    coefficients: CoefRow[];
    design_columns: string[];
  };
  text: string;
  r_set: Record<string, unknown>;
  e_set: Record<string, unknown> | null;
}

// ===================================================================
// Postestimation
// ===================================================================

export interface MarginsRow {
  name: string;
  dy_dx: number | null;
  se: number | null;
  z: number | null;
  p: number | null;
  ci_low: number | null;
  ci_high: number | null;
  significant: boolean;
}

export interface MarginsResponse {
  command: string;
  result: {
    kind: "margins";
    at_means: boolean;
    rows: MarginsRow[];
    depvar: string;
    for_command: "regress" | "logit";
  };
  text: string;
  r_set: Record<string, unknown>;
  e_set: Record<string, unknown> | null;
}

export interface PredictResponse {
  command: string;
  result: {
    kind: "predict";
    new_var: string;
    predict_kind: string;
    label: string;
    n_filled: number;
  };
  text: string;
  r_set: Record<string, unknown>;
  e_set: Record<string, unknown> | null;
}

export interface TestResponse {
  command: string;
  result: {
    kind: "test";
    restrictions: string[];
    F: number | null;
    chi2: number | null;
    p: number | null;
    df_num: number | null;
    df_denom: number | null;
  };
  text: string;
  r_set: Record<string, unknown>;
  e_set: Record<string, unknown> | null;
}

// Mode-toggle preserves: any analyze result we've seen, plus the last
// estimation context so postestimation buttons remain meaningful.
export interface AnalyzeRecord {
  command: string;
  kind: "regress" | "logit" | "margins" | "predict" | "test" | "lincom" | "estat_ic" | "estat_vif";
  payload: unknown;
  text: string;
  timestamp: number;
}
