/* Typed API client. Vite proxies /api and /healthz to FastAPI on :8000. */

import type {
  ColumnsResponse,
  HistogramResponse,
  LogitResponse,
  MarginsResponse,
  PredictResponse,
  RegressResponse,
  SummarizeResult,
  TabulateResult,
  TestResponse,
  UploadOrChoice,
  UploadResponse,
} from "./types";

const baseFetch = async (input: string, init: RequestInit = {}): Promise<Response> => {
  const resp = await fetch(input, {
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
};
