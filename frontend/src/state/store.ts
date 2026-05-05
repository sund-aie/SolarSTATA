/* Global app state.
 *
 * Mode, dataset, selected variable, and per-variable summarize results are all
 * preserved across mode switches — that's the spec contract. Zustand keeps
 * the surface tiny and explicit.
 */

import { create } from "zustand";
import type { ColumnInfo, Dataset, Mode, Step, SummarizeResult } from "../lib/types";

export interface AppState {
  mode: Mode;
  setMode: (m: Mode) => void;

  step: Step;
  setStep: (s: Step) => void;

  dataset: Dataset | null;
  columns: ColumnInfo[];
  setDataset: (d: Dataset, columns: ColumnInfo[]) => void;
  resetDataset: () => void;

  selectedVar: string | null;
  selectVar: (name: string | null) => void;

  // Cache summarize results by variable list key so we don't re-fetch on
  // re-selection. Key = variable names sorted joined by space.
  summarizeCache: Record<string, SummarizeResult>;
  setSummarize: (key: string, result: SummarizeResult) => void;

  commandHistory: string[];
  appendCommand: (cmd: string) => void;
}

export const useApp = create<AppState>((set) => ({
  mode: "guided",
  setMode: (m) => set({ mode: m }),

  step: "import",
  setStep: (s) => set({ step: s }),

  dataset: null,
  columns: [],
  setDataset: (dataset, columns) => set({ dataset, columns, step: "inspect" }),
  resetDataset: () => set({ dataset: null, columns: [], selectedVar: null, step: "import" }),

  selectedVar: null,
  selectVar: (name) => set({ selectedVar: name }),

  summarizeCache: {},
  setSummarize: (key, result) =>
    set((s) => ({ summarizeCache: { ...s.summarizeCache, [key]: result } })),

  commandHistory: [],
  appendCommand: (cmd) => set((s) => ({ commandHistory: [...s.commandHistory, cmd] })),
}));

export const summarizeKey = (variables: string[], detail: boolean): string =>
  `${[...variables].sort().join(" ")}::detail=${detail}`;
