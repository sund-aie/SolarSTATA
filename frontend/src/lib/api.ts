/* Typed API client. Vite proxies /api and /healthz to FastAPI on :8000. */

import type {
  ColumnsResponse,
  HistogramResponse,
  SummarizeResult,
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

  upload: async (file: File): Promise<UploadResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await baseFetch("/api/data/upload", { method: "POST", body: fd });
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
};
