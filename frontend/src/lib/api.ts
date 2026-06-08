/* Typed API client. Vite proxies /api and /healthz to FastAPI on :8000.
 *
 * When running inside the Electron shell, `window.electronAPI` is
 * exposed by preload.ts and reports the dynamic sidecar port. We
 * resolve a full absolute URL (http://127.0.0.1:<port>/...) and
 * skip the Vite proxy entirely.
 */

import type {
  AnovaRmResponse,
  AnovaTwoResponse,
  ColumnsResponse,
  HistogramResponse,
  LeveneResponse,
  LogitResponse,
  MarginsResponse,
  OnewayResponse,
  PredictResponse,
  PreflightResponse,
  RegressResponse,
  ShapiroResponse,
  SummarizeResult,
  TabstatResponse,
  TabulateResult,
  TestResponse,
  UploadOrChoice,
  UploadResponse,
} from "./types";
import { apiBase } from "./electron";

const resolveUrl = async (p: string): Promise<string> => {
  if (/^[a-z]+:\/\//i.test(p)) return p;
  const base = await apiBase();
  if (!base) return p;
  return base + (p.startsWith("/") ? p : "/" + p);
};

const baseFetch = async (input: string, init: RequestInit = {}): Promise<Response> => {
  const url = await resolveUrl(input);
  const resp = await fetch(url, {
    credentials: "include", // cookies for session
    ...init,
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new ApiError(resp.status, detail || resp.statusText);
  }
  return resp;
};

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export const api = {
  health: async () => {
    const resp = await baseFetch("/healthz");
    return (await resp.json()) as { status: string; version: string; phase: number };
  },

  upload: async (file: File, opts: { sheet?: string; headerRow?: number } = {}): Promise<UploadOrChoice> => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.sheet) fd.append("sheet", opts.sheet);
    if (opts.headerRow != null) fd.append("header_row", String(opts.headerRow));
    const resp = await baseFetch("/api/data/upload", { method: "POST", body: fd });
    return (await resp.json()) as UploadOrChoice;
  },

  finalizeUpload: async (params: {
    file_id: string;
    sheet: string | null;
    header_row: number;
  }): Promise<UploadResponse> => {
    const resp = await baseFetch("/api/data/upload/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    return (await resp.json()) as UploadResponse;
  },

  preflight: async (params: {
    file_id: string;
    sheet?: string | null;
  }): Promise<PreflightResponse> => {
    const resp = await baseFetch("/api/data/preflight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    return (await resp.json()) as PreflightResponse;
  },

  columns: async (frame = "default"): Promise<ColumnsResponse> => {
    const resp = await baseFetch(`/api/data/columns?frame=${encodeURIComponent(frame)}`);
    return (await resp.json()) as ColumnsResponse;
  },

  histogram: async (variable: string, bins = 15, frame = "default"): Promise<HistogramResponse> => {
    const params = new URLSearchParams({ var: variable, bins: String(bins), frame });
    const resp = await baseFetch(`/api/data/histogram?${params}`);
    return (await resp.json()) as HistogramResponse;
  },

  summarize: async (
    variables: string[],
    detail = false,
    frame = "default",
  ): Promise<SummarizeResult> => {
    const resp = await baseFetch("/api/stats/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame, variables, detail }),
    });
    return (await resp.json()) as SummarizeResult;
  },

  tabulate: async (
    var1: string,
    var2: string | null = null,
    frame = "default",
  ): Promise<TabulateResult> => {
    const resp = await baseFetch("/api/stats/tabulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame, var1, var2 }),
    });
    return (await resp.json()) as TabulateResult;
  },

  tabstat: async (params: {
    variables: string[];
    by?: string | null;
    stats?: string[] | null;
    missing?: boolean;
    frame?: string;
  }): Promise<TabstatResponse> => {
    const resp = await baseFetch("/api/stats/tabstat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", ...params }),
    });
    return (await resp.json()) as TabstatResponse;
  },

  oneway: async (params: {
    depvar: string;
    groupvar: string;
    posthoc?: "none" | "bonferroni" | "scheffe" | "sidak";
    if_expr?: string | null;
    frame?: string;
  }): Promise<OnewayResponse> => {
    const resp = await baseFetch("/api/stats/oneway", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", posthoc: "none", ...params }),
    });
    return (await resp.json()) as OnewayResponse;
  },

  anovaTwo: async (params: {
    depvar: string;
    factor_a: string;
    factor_b: string;
    interaction?: boolean;
    frame?: string;
  }): Promise<AnovaTwoResponse> => {
    const resp = await baseFetch("/api/stats/anova_two", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", interaction: true, ...params }),
    });
    return (await resp.json()) as AnovaTwoResponse;
  },

  anovaRm: async (params: {
    depvar: string;
    subject: string;
    within: string;
    between?: string | null;
    correction?: "none" | "gg" | "hf";
    frame?: string;
  }): Promise<AnovaRmResponse> => {
    const resp = await baseFetch("/api/stats/anova_rm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", correction: "none", ...params }),
    });
    return (await resp.json()) as AnovaRmResponse;
  },

  shapiro: async (params: { var: string; by?: string | null; frame?: string }): Promise<ShapiroResponse> => {
    const resp = await baseFetch("/api/stats/shapiro", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", ...params }),
    });
    return (await resp.json()) as ShapiroResponse;
  },

  levene: async (params: {
    depvar: string;
    groupvar: string;
    center?: "median" | "mean" | "trimmed";
    frame?: string;
  }): Promise<LeveneResponse> => {
    const resp = await baseFetch("/api/stats/levene", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", center: "median", ...params }),
    });
    return (await resp.json()) as LeveneResponse;
  },

  regress: async (params: {
    depvar: string;
    indepvars: string[];
    vce?: "ols" | "robust" | "hc3" | "cluster";
    cluster?: string | null;
    if_expr?: string | null;
    in_range?: string | null;
    frame?: string;
  }): Promise<RegressResponse> => {
    const resp = await baseFetch("/api/stats/regress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", vce: "ols", ...params }),
    });
    return (await resp.json()) as RegressResponse;
  },

  logit: async (params: {
    depvar: string;
    indepvars: string[];
    odds_ratios?: boolean;
    vce?: "mle" | "robust" | "cluster";
    cluster?: string | null;
    if_expr?: string | null;
    in_range?: string | null;
    frame?: string;
  }): Promise<LogitResponse> => {
    const resp = await baseFetch("/api/stats/logit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame: "default", vce: "mle", ...params }),
    });
    return (await resp.json()) as LogitResponse;
  },

  margins: async (atMeans = false): Promise<MarginsResponse> => {
    const resp = await baseFetch("/api/stats/postest/margins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ at_means: atMeans }),
    });
    return (await resp.json()) as MarginsResponse;
  },

  predictFitted: async (params: {
    new_var?: string;
    kind?: "xb" | "resid" | "pr";
  } = {}): Promise<PredictResponse> => {
    const resp = await baseFetch("/api/stats/postest/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_var: "fitted_values", kind: "xb", ...params }),
    });
    return (await resp.json()) as PredictResponse;
  },

  test: async (restrictions: string[]): Promise<TestResponse> => {
    const resp = await baseFetch("/api/stats/postest/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ restrictions }),
    });
    return (await resp.json()) as TestResponse;
  },

  // ===== Graphs =====
  // body accepts `subgroup` for grouped bar charts (B1 in v3.0.2).
  graph: async (
    kind: "histogram" | "scatter" | "box" | "bar" | "line" | "counts" | "residuals" | "marginsplot",
    body: Record<string, unknown> = {},
  ): Promise<{ command: string; kind: "graph"; figure: { data: unknown[]; layout: Record<string, unknown> } }> => {
    const path = kind === "residuals"
      ? "/api/graphs/residuals"
      : kind === "marginsplot"
      ? "/api/graphs/marginsplot"
      : `/api/graphs/${kind}`;
    const resp = await baseFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await resp.json();
  },

  // ===== Exports =====
  downloadDataset: async (format: "csv" | "xlsx" | "dta" | "parquet"): Promise<Blob> => {
    const resp = await baseFetch(`/api/export/dataset?format=${format}`);
    return await resp.blob();
  },

  downloadDoFile: async (): Promise<Blob> => {
    const resp = await baseFetch("/api/export/dofile");
    return await resp.blob();
  },

  downloadReport: async (format: "pdf" | "html"): Promise<Blob> => {
    const resp = await baseFetch(`/api/export/report?format=${format}`);
    return await resp.blob();
  },

  exportCapabilities: async (): Promise<{
    pdf: boolean;
    html: boolean;
    do_file: boolean;
    dataset_formats: string[];
    pdf_unavailable_reason: string | null;
  }> => {
    const resp = await baseFetch("/api/export/capabilities");
    return await resp.json();
  },

  downloadWorkspace: async (): Promise<Blob> => {
    const resp = await baseFetch("/api/workspace/download");
    return await resp.blob();
  },

  uploadWorkspace: async (file: File): Promise<UploadResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await baseFetch("/api/workspace/upload", { method: "POST", body: fd });
    return (await resp.json()) as UploadResponse;
  },
};
