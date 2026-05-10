/* Global app state.
 *
 * Mode, dataset, selected variable, and per-variable summarize results are all
 * preserved across mode switches — that's the spec contract. Zustand keeps
 * the surface tiny and explicit.
 */

import { create } from "zustand";
import type {
  AnalyzeRecord,
  ColumnInfo,
  Dataset,
  Mode,
  Step,
  SummarizeResult,
} from "../lib/types";

export interface LastEstimation {
  command: string;
  cmd_kind: "regress" | "logit";
  depvar: string;
  indepvars: string[];
  designColumns: string[];
}

export interface AppState {
  mode: Mode;
  setMode: (m: Mode) => void;

  step: Step;
  setStep: (s: Step) => void;

  dataset: Dataset | null;
  columns: ColumnInfo[];
  setDataset: (d: Dataset, columns: ColumnInfo[]) => void;
  refreshColumns: (columns: ColumnInfo[]) => void;
  resetDataset: () => void;

  selectedVar: string | null;
  selectVar: (name: string | null) => void;

  // Cache summarize results by variable list key so we don't re-fetch on
  // re-selection. Key = variable names sorted joined by space.
  summarizeCache: Record<string, SummarizeResult>;
  setSummarize: (key: string, result: SummarizeResult) => void;

  // Analyze step: ordered list of result blocks the user has produced this session.
  analyzeRecords: AnalyzeRecord[];
  pushAnalyzeRecord: (r: AnalyzeRecord) => void;
  clearAnalyzeRecords: () => void;

  // The last estimation context — drives postestimation buttons and the
  // command-preview footer in the Analyze step.
  lastEstimation: LastEstimation | null;
  setLastEstimation: (e: LastEstimation | null) => void;

  commandHistory: string[];
  appendCommand: (cmd: string) => void;

  helpOpen: boolean;
  toggleHelp: (open?: boolean) => void;
}

export const useApp = create<AppState>((set) => ({
  mode: "guided",
  setMode: (m) => set({ mode: m }),

  step: "import",
  setStep: (s) => set({ step: s }),

  dataset: null,
  columns: [],
  setDataset: (dataset, columns) => set({ dataset, columns, step: "inspect" }),
  refreshColumns: (columns) => set({ columns }),
  resetDataset: () =>
    set({
      dataset: null,
      columns: [],
      selectedVar: null,
      step: "import",
      analyzeRecords: [],
      lastEstimation: null,
      summarizeCache: {},
    }),

  selectedVar: null,
  selectVar: (name) => set({ selectedVar: name }),

  summarizeCache: {},
  setSummarize: (key, result) =>
    set((s) => ({ summarizeCache: { ...s.summarizeCache, [key]: result } })),

  analyzeRecords: [],
  pushAnalyzeRecord: (r) => set((s) => ({ analyzeRecords: [...s.analyzeRecords, r] })),
  clearAnalyzeRecords: () => set({ analyzeRecords: [], lastEstimation: null }),

  lastEstimation: null,
  setLastEstimation: (e) => set({ lastEstimation: e }),

  commandHistory: [],
  appendCommand: (cmd) => set((s) => ({ commandHistory: [...s.commandHistory, cmd] })),

  helpOpen: false,
  toggleHelp: (open) => set((s) => ({ helpOpen: open ?? !s.helpOpen })),
}));

export const summarizeKey = (variables: string[], detail: boolean): string =>
  `${[...variables].sort().join(" ")}::detail=${detail}`;
