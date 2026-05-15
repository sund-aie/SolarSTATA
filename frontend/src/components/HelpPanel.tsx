/* Help side panel — slides in from the right.
 *
 * Three tabs:
 *   - Walkthroughs: 5 narrative tutorials based on clinic_patients.csv.
 *   - Commands: searchable command reference.
 *   - Which test?: decision tree mapping research questions → SolarSTATA commands.
 *
 * Trigger: topbar `?` button, the floating tip, or pressing `?` (handled at
 * the App level via a keyboard listener).
 */

import { useMemo, useState } from "react";
import { useApp } from "../state/store";
import { WALKTHROUGHS, type Walkthrough, type WalkthroughStep, type StepAction } from "../lib/walkthroughs";
import { api } from "../lib/api";

interface Props {
  onClose: () => void;
}

type Tab = "walkthroughs" | "commands" | "which_test";

export function HelpPanel({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>("walkthroughs");
  const [active, setActive] = useState<Walkthrough | null>(null);

  return (
    <div
      className="fixed top-[56px] right-0 bottom-0 w-[440px] bg-bg border-l border-border shadow-elevated z-40 flex flex-col"
      role="dialog"
      aria-label="Help panel"
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <div className="font-serif italic text-[18px] text-text">Help</div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close help"
          className="text-text-muted hover:text-text text-[18px]"
        >
          ×
        </button>
      </div>

      <div className="flex border-b border-border">
        <TabButton active={tab === "walkthroughs"} onClick={() => { setTab("walkthroughs"); setActive(null); }}>
          Walkthroughs
        </TabButton>
        <TabButton active={tab === "commands"} onClick={() => { setTab("commands"); setActive(null); }}>
          Commands
        </TabButton>
        <TabButton active={tab === "which_test"} onClick={() => { setTab("which_test"); setActive(null); }}>
          Which test?
        </TabButton>
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === "walkthroughs" && !active && <WalkthroughList onPick={setActive} />}
        {tab === "walkthroughs" && active && <WalkthroughRunner walkthrough={active} onBack={() => setActive(null)} />}
        {tab === "commands" && <CommandReference />}
        {tab === "which_test" && <WhichTestTree />}
      </div>
    </div>
  );
}

function TabButton({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-4 py-3 text-[13px] font-medium transition-colors ${
        active ? "text-text border-b-2 border-accent -mb-px bg-surface" : "text-text-muted hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

// =====================================================================
// Walkthroughs
// =====================================================================

function WalkthroughList({ onPick }: { onPick: (w: Walkthrough) => void }) {
  return (
    <div className="p-4 space-y-3">
      <div className="text-[13px] text-text-muted">
        Five narrative tutorials based on the bundled clinic_patients dataset. Each
        walkthrough is a short read; you click through the app yourself, but every
        step shows the equivalent Stata syntax so you pick it up over time.
      </div>
      {WALKTHROUGHS.map((w, i) => (
        <button
          key={w.id}
          type="button"
          onClick={() => onPick(w)}
          className="block w-full text-left bg-surface border border-border rounded-md p-4 hover:border-border-strong hover:bg-surface-2 transition-colors"
        >
          <div className="flex items-baseline justify-between mb-1">
            <div className="font-serif italic text-[16px] text-text">
              <span className="font-mono not-italic text-[12px] text-accent mr-2">{i + 1}</span>
              {w.title}
            </div>
            {w.deferred && (
              <span className="font-mono text-[10px] uppercase tracking-[0.08em] px-2 py-[2px] bg-warn-soft text-warn rounded">
                {w.deferred.phase}
              </span>
            )}
          </div>
          <div className="text-[12px] text-text-muted leading-snug">{w.blurb}</div>
        </button>
      ))}
    </div>
  );
}

function WalkthroughRunner({ walkthrough, onBack }: { walkthrough: Walkthrough; onBack: () => void }) {
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setDataset = useApp((s) => s.setDataset);
  const setStep = useApp((s) => s.setStep);
  const selectVar = useApp((s) => s.selectVar);
  const appendCommand = useApp((s) => s.appendCommand);

  if (walkthrough.deferred) {
    return (
      <div className="p-5 space-y-3">
        <button onClick={onBack} className="text-[12px] text-text-muted hover:text-text">← All walkthroughs</button>
        <div className="font-serif italic text-[18px] text-text">{walkthrough.title}</div>
        <div className="bg-warn-soft border border-warn rounded-md p-4 text-[13px] text-text">
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-warn mb-2">
            Lands in {walkthrough.deferred.phase}
          </div>
          <div className="text-text">{walkthrough.deferred.reason}</div>
        </div>
      </div>
    );
  }

  const step: WalkthroughStep | undefined = walkthrough.steps[idx];
  if (!step) return null;
  const isLast = idx === walkthrough.steps.length - 1;

  const runAction = async (action: StepAction) => {
    if (!action) return;
    setBusy(true);
    setError(null);
    try {
      if (action.kind === "load_clinic") {
        const resp = await fetch("/api/walkthroughs/datasets/clinic_patients.csv", { credentials: "include" });
        if (!resp.ok) throw new Error("Could not fetch bundled dataset");
        const blob = await resp.blob();
        const file = new File([blob], "clinic_patients.csv", { type: "text/csv" });
        const result = await api.upload(file);
        if ("requires_choice" in result) {
          throw new Error("Bundled dataset unexpectedly required a sheet choice");
        }
        const cols = await api.columns(result.frame);
        setDataset(
          { filename: result.filename, n_obs: result.n_obs, n_vars: result.n_vars, columns: result.columns },
          cols.columns,
        );
        appendCommand(`use "${result.filename}", clear`);
      } else if (action.kind === "go_step") {
        setStep(action.step);
      } else if (action.kind === "select_var") {
        setStep("inspect");
        selectVar(action.name);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-[12px] text-text-muted hover:text-text">
          ← All walkthroughs
        </button>
        <div className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
          Step {idx + 1} of {walkthrough.steps.length}
        </div>
      </div>

      <div className="font-serif italic text-[16px] text-accent">{walkthrough.title}</div>
      <div className="font-serif italic text-[20px] text-text leading-snug">{step.title}</div>
      <div className="text-[13px] text-text-muted leading-relaxed whitespace-pre-line">{step.body}</div>

      {step.command && (
        <div>
          <div className="eyebrow mb-2">Pro syntax</div>
          <pre className="font-mono text-[12px] text-text bg-surface border border-border rounded-sm p-3 whitespace-pre-wrap">{step.command}</pre>
        </div>
      )}

      {step.action && (
        <button
          type="button"
          onClick={() => runAction(step.action!)}
          disabled={busy}
          className="run-btn-primary disabled:opacity-60 !w-auto"
        >
          {busy
            ? "Running…"
            : step.action.kind === "load_clinic"
            ? "Load the bundled dataset"
            : step.action.kind === "go_step"
            ? `Take me to ${step.action.step}`
            : step.action.kind === "select_var"
            ? `Open ${step.action.name}`
            : "Run"}
        </button>
      )}

      {error && <div className="text-[12px] text-warn">{error}</div>}

      <div className="flex items-center justify-between pt-3 border-t border-border">
        <button
          type="button"
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          disabled={idx === 0}
          className="text-[12px] text-text-muted hover:text-text disabled:opacity-40"
        >
          ← Previous
        </button>
        {!isLast ? (
          <button
            type="button"
            onClick={() => setIdx((i) => i + 1)}
            className="bg-surface-2 text-text border border-border-strong px-4 py-[6px] rounded-sm text-[12px] font-medium hover:bg-surface-3"
          >
            Next →
          </button>
        ) : (
          <button
            type="button"
            onClick={onBack}
            className="bg-accent text-bg px-4 py-[6px] rounded-sm text-[12px] font-medium hover:brightness-110"
          >
            Done
          </button>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// Command reference
// =====================================================================

interface CommandDoc {
  cmd: string;
  syntax: string;
  desc: string;
  example: string;
}

const COMMANDS: CommandDoc[] = [
  { cmd: "summarize", syntax: "summarize [varlist] [, detail]",
    desc: "Mean, SD, min, max for numeric variables. detail adds percentiles + skew/kurtosis.",
    example: "summarize plaque_index gingival_index, detail" },
  { cmd: "tabulate", syntax: "tabulate var1 [var2]",
    desc: "Frequency or cross-tabulation. Two args = contingency table.",
    example: "tabulate sex caries" },
  { cmd: "regress", syntax: "regress y x1 x2 [if exp] [in range] [, vce(robust|hc3|cluster id)]",
    desc: "OLS linear regression with optional robust/cluster SEs and factor-variable predictors (i./c./##).",
    example: "regress plaque_index age i.sex brushing_freq, vce(robust)" },
  { cmd: "logit", syntax: "logit y x1 x2 [if exp] [, or vce(robust)]",
    desc: "Binary logistic regression. or option displays odds ratios.",
    example: "logit caries age smoking, or" },
  { cmd: "logistic", syntax: "logistic y x1 x2 [if exp] [, vce(robust)]",
    desc: "Same as logit but reports odds ratios by default.",
    example: "logistic caries age smoking" },
  { cmd: "predict", syntax: "predict newvar [, xb | resid | pr | stdp]",
    desc: "Generate fitted values (xb), residuals (resid), or fitted probabilities (pr after logit) into a new variable.",
    example: "predict yhat\npredict prob, pr" },
  { cmd: "margins", syntax: "margins [, atmeans]",
    desc: "Average marginal effects (AME by default) of every predictor on the outcome scale.",
    example: "margins" },
  { cmd: "test", syntax: "test coefname [coefname …]",
    desc: "Wald test that one or more coefficients are zero (joint).",
    example: "test brushing_freq" },
  { cmd: "lincom", syntax: "lincom expression",
    desc: "Linear combination of coefficients. Supports `2*x`, `x + y`, `x - y`.",
    example: "lincom 2*brushing_freq" },
  { cmd: "estat ic", syntax: "estat ic", desc: "AIC and BIC for the last estimation.",
    example: "estat ic" },
  { cmd: "estat vif", syntax: "estat vif", desc: "Variance inflation factors (after regress).",
    example: "estat vif" },
  { cmd: "tabstat", syntax: "tabstat varlist [, by(group) stats(n mean sd min max median p25 p75 sum)]",
    desc: "By-group descriptives matrix. Pick any subset of stats; without by() you get one row per variable.",
    example: "tabstat plaque_index gingival_index, by(sex) stats(n mean sd)" },
  { cmd: "oneway", syntax: "oneway depvar groupvar [, bonferroni | scheffe | sidak]",
    desc: "One-way ANOVA. Bartlett's test for equal variances is always appended. Optional posthoc pairwise comparisons.",
    example: "oneway plaque_index brushing_freq, bonferroni" },
  { cmd: "anova", syntax: "anova depvar factor_a##factor_b   |   anova depvar subj##time, repeated(time) [gg|hf]",
    desc: "Two-way ANOVA with optional interaction (a##b) or repeated-measures with sphericity correction (gg = Greenhouse-Geisser, hf = Huynh-Feldt).",
    example: "anova plaque_index sex##brushing_freq" },
  { cmd: "swilk", syntax: "swilk var [, by(group)]",
    desc: "Shapiro-Wilk test for normality. Optional by-group reports the test per level.",
    example: "swilk plaque_index, by(sex)" },
  { cmd: "robvar", syntax: "robvar depvar, by(group) [, median | mean | trimmed]",
    desc: "Levene's test for equal variances across groups. Default center = median (Brown-Forsythe variant).",
    example: "robvar plaque_index, by(brushing_freq)" },
];

function CommandReference() {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return COMMANDS;
    return COMMANDS.filter((c) =>
      c.cmd.toLowerCase().includes(term)
      || c.syntax.toLowerCase().includes(term)
      || c.desc.toLowerCase().includes(term),
    );
  }, [q]);

  return (
    <div className="p-4 space-y-3">
      <input
        type="text"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search commands…"
        className="w-full bg-bg border border-border rounded-sm px-3 py-2 font-mono text-[12px] text-text"
      />
      {filtered.map((c) => (
        <div key={c.cmd} className="bg-surface border border-border rounded-md p-3">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-mono text-[14px] font-semibold text-accent">{c.cmd}</span>
            <span className="font-mono text-[11px] text-text-faint">{c.syntax}</span>
          </div>
          <div className="text-[12px] text-text-muted mb-2">{c.desc}</div>
          <pre className="font-mono text-[11px] text-text bg-bg border border-border rounded-sm p-2 whitespace-pre-wrap">{c.example}</pre>
        </div>
      ))}
      {filtered.length === 0 && (
        <div className="text-[12px] text-text-faint italic">No commands match "{q}".</div>
      )}
    </div>
  );
}

// =====================================================================
// "Which test?" decision tree
// =====================================================================

interface TestNode {
  q: string;
  branches: { label: string; out?: { cmd: string; why: string }; next?: TestNode }[];
}

const TREE: TestNode = {
  q: "What kind of outcome?",
  branches: [
    {
      label: "Continuous (e.g. plaque index, blood pressure)",
      next: {
        q: "How many groups are you comparing?",
        branches: [
          {
            label: "Two independent groups",
            next: {
              q: "Are the values approximately normal? (swilk p > 0.05)",
              branches: [
                {
                  label: "Yes — normal",
                  out: { cmd: "ttest (lands in v3.1)",
                         why: "For now: oneway y g with two levels gives the same F = t² result. Bartlett's test built-in checks equal variances." },
                },
                {
                  label: "No — skewed",
                  out: { cmd: "Mann-Whitney (lands in v3.1)",
                         why: "Until v3.1, oneway with bonferroni posthoc is the closest we ship — but the assumption violation matters for small n." },
                },
              ],
            },
          },
          {
            label: "Three or more independent groups",
            next: {
              q: "Are within-group values approximately normal?",
              branches: [
                {
                  label: "Yes — and variances roughly equal (Bartlett p > 0.05)",
                  out: { cmd: "oneway y g",
                         why: "Bartlett's test always runs; check it on the result card. Add , bonferroni / scheffe / sidak for pairwise posthoc." },
                },
                {
                  label: "Yes — but variances differ",
                  out: { cmd: "oneway y g (note Bartlett's p)",
                         why: "Welch's ANOVA lands in v3.1. For now, report the Bartlett violation alongside the oneway result." },
                },
                {
                  label: "No — non-normal",
                  out: { cmd: "Kruskal-Wallis (lands in v3.1)",
                         why: "For now: tabstat by group + a box plot to describe; non-parametric inference arrives in v3.1." },
                },
              ],
            },
          },
          {
            label: "Repeated measures on the same subject (e.g. timepoints)",
            next: {
              q: "Do you also have between-subject groups?",
              branches: [
                {
                  label: "No — just within-subject (time only)",
                  out: { cmd: "anova_rm with within = time",
                         why: "Add gg or hf correction if sphericity is in doubt (it usually is)." },
                },
                {
                  label: "Yes — within × between (e.g. groups × timepoints)",
                  out: { cmd: "anova_rm with within = time, between = group",
                         why: "We fit the within model and surface the between effect via subject-level means (split-plot workaround). Full mixed-effects lands in v3.1." },
                },
              ],
            },
          },
          {
            label: "Continuous predictor (not groups)",
            out: { cmd: "regress y x1 x2 … , vce(robust)",
                   why: "OLS with HC3 / cluster SE if needed. Add i.factor for categorical predictors. margins / predict / test available under the result card." },
          },
        ],
      },
    },
    {
      label: "Binary (yes/no, presence/absence)",
      next: {
        q: "What's your goal?",
        branches: [
          {
            label: "Compare proportions across groups",
            out: { cmd: "tabulate x y",
                   why: "Two-way contingency with chi-squared. Use for sex × caries, treatment × cure, etc." },
          },
          {
            label: "Model probability from continuous predictors",
            out: { cmd: "logit y x1 x2 … , or",
                   why: "Logistic regression with odds ratios. Add vce(robust) for clustered data; margins gives predicted probabilities." },
          },
        ],
      },
    },
    {
      label: "Just describing one variable (no comparison)",
      out: { cmd: "summarize y, detail  •  swilk y  •  histogram y",
             why: "Start with descriptives + a Shapiro check to decide if downstream tests should be parametric or not." },
    },
  ],
};

function WhichTestTree() {
  const [path, setPath] = useState<TestNode[]>([TREE]);
  const [pickedLabels, setPickedLabels] = useState<string[]>([]);
  const [terminal, setTerminal] = useState<{ cmd: string; why: string } | null>(null);

  const current = path[path.length - 1];

  const reset = () => {
    setPath([TREE]);
    setPickedLabels([]);
    setTerminal(null);
  };

  const pick = (branch: TestNode["branches"][number]) => {
    setPickedLabels((p) => [...p, branch.label]);
    if (branch.out) {
      setTerminal(branch.out);
    } else if (branch.next) {
      setPath((p) => [...p, branch.next!]);
    }
  };

  const goBack = () => {
    if (terminal) {
      setTerminal(null);
      setPickedLabels((p) => p.slice(0, -1));
      return;
    }
    if (path.length > 1) {
      setPath((p) => p.slice(0, -1));
      setPickedLabels((p) => p.slice(0, -1));
    }
  };

  return (
    <div className="p-4 space-y-3">
      <div className="text-[12px] text-text-muted">
        Click through the questions to find the right test for your data.
        Tests not yet shipping in v3.0.2 are flagged with their planned
        release.
      </div>

      {pickedLabels.length > 0 && (
        <div className="text-[11px] text-text-faint font-mono whitespace-pre-wrap leading-relaxed">
          {pickedLabels.map((l, i) => `${"  ".repeat(i)}↳ ${l}`).join("\n")}
        </div>
      )}

      {!terminal ? (
        <>
          <div className="font-serif italic text-[16px] text-text">{current.q}</div>
          <div className="space-y-2">
            {current.branches.map((b, i) => (
              <button
                key={i}
                type="button"
                onClick={() => pick(b)}
                className="block w-full text-left bg-surface border border-border rounded-md p-3 hover:border-border-strong hover:bg-surface-2 transition-colors text-[13px] text-text"
              >
                {b.label}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="bg-surface border border-accent rounded-md p-4 space-y-2">
          <div className="eyebrow text-accent">Run this</div>
          <pre className="font-mono text-[13px] text-text bg-bg border border-border rounded-sm p-3 whitespace-pre-wrap">{terminal.cmd}</pre>
          <div className="text-[12px] text-text-muted leading-relaxed">{terminal.why}</div>
        </div>
      )}

      <div className="flex items-center justify-between pt-3 border-t border-border">
        <button
          type="button"
          onClick={goBack}
          disabled={path.length === 1 && !terminal}
          className="text-[12px] text-text-muted hover:text-text disabled:opacity-40"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={reset}
          disabled={path.length === 1 && !terminal && pickedLabels.length === 0}
          className="text-[12px] text-text-muted hover:text-text disabled:opacity-40"
        >
          Start over
        </button>
      </div>
    </div>
  );
}
