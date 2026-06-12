/* Static walkthrough catalog — narrative tutorials referencing the
 * bundled clinic_patients dataset. Each step has prose, an optional
 * Stata command equivalent, and an optional auto-action the runner
 * can execute (currently only `load_clinic`).
 */

export type StepAction =
  | { kind: "load_clinic" }
  | { kind: "go_step"; step: "import" | "inspect" | "analyze" | "visualize" | "export" }
  | { kind: "select_var"; name: string }
  | null;

export interface WalkthroughStep {
  title: string;
  body: string;
  command?: string;
  action?: StepAction;
}

export interface Walkthrough {
  id: string;
  title: string;
  blurb: string;
  steps: WalkthroughStep[];
  /** When true, the runner shows a "lands in a later phase" placeholder
   *  instead of stepping through. */
  deferred?: { phase: string; reason: string };
}

export const WALKTHROUGHS: Walkthrough[] = [
  // -----------------------------------------------------------------
  {
    id: "stack-and-inspect",
    title: "Stack and inspect raw data",
    blurb:
      "Load the bundled clinic dataset, eyeball the variable types and missingness, " +
      "and run your first descriptives.",
    steps: [
      {
        title: "Load clinic_patients.csv",
        body:
          "We'll load the bundled synthetic dental dataset — 400 fictional patients " +
          "plus six obviously-dirty test rows. Press Load to drop it straight into the importer.",
        command: 'use "clinic_patients.csv", clear',
        action: { kind: "load_clinic" },
      },
      {
        title: "Look at the variable cards",
        body:
          "Switch to Inspect. Each card shows the variable name, type chip (numeric / binary / " +
          "categorical / id), n, missing %, and a tiny distribution. Watch the warm orange " +
          "missing-% badges on plaque_index, gingival_index, and brushing_freq.",
        action: { kind: "go_step", step: "inspect" },
      },
      {
        title: "Click plaque_index to drill in",
        body:
          "Click the plaque_index card. The right rail fills with a 2×2 stats grid, a " +
          "distribution histogram, and a Run summarize button.",
        action: { kind: "select_var", name: "plaque_index" },
      },
      {
        title: "Run summarize",
        body:
          "Click Run summarize on the inspect rail. You should see N=379 (out of 406, missing " +
          "the 27 we MCAR-injected), Mean ≈ 1.44, Min = -0.5 (a dirty value!), Max = 8.0 (also " +
          "dirty). That's the cue that the next step in real research is cleaning.",
        command: "summarize plaque_index",
      },
    ],
  },

  // -----------------------------------------------------------------
  {
    id: "clean-and-recode",
    title: "Clean and recode",
    blurb:
      "Drop the dirty rows, recode Yes/No → 1/0, label values, and generate a new " +
      "variable from existing ones.",
    steps: [],
    deferred: {
      phase: "Phase 4.1",
      reason:
        "Data manipulation commands (drop, recode, generate, egen, label) ship in a " +
        "follow-up slice. Once they land, this walkthrough will guide you through " +
        "filtering patient_id ≥ 9000, recoding sex into a binary, and computing a " +
        "plaque-improvement variable.",
    },
  },

  // -----------------------------------------------------------------
  {
    id: "first-regression",
    title: "Run your first regression",
    blurb:
      "Linear regression of plaque on age, sex, and brushing frequency, with " +
      "robust standard errors. Read the output table and interpret the coefficients.",
    steps: [
      {
        title: "Load the data",
        body: "If you haven't already, load the bundled dataset.",
        command: 'use "clinic_patients.csv", clear',
        action: { kind: "load_clinic" },
      },
      {
        title: "Open the Analyze step",
        body:
          "Jump to Analyze and stay on the Regression tab. We'll fill in the OLS form.",
        action: { kind: "go_step", step: "analyze" },
      },
      {
        title: "Build the model",
        body:
          "Outcome = plaque_index. Add three predictors: age (auto = continuous), " +
          "sex (use the i. toggle to treat as categorical), brushing_freq. Tick Robust SE " +
          "to use Stata's vce(robust) (HC1).",
        command: "regress plaque_index age i.sex brushing_freq, vce(robust)",
      },
      {
        title: "Read the result",
        body:
          "Hit Run regression. The header card shows N, F, R², and Root MSE. The coef " +
          "table shows brushing_freq with a strongly negative coefficient and a gold dot " +
          "(p < 0.05) — more brushing → less plaque. age and sex won't be significant on " +
          "this synthetic data.",
      },
      {
        title: "Run residual diagnostics",
        body:
          "Switch to the Postestimation tab. Click Predict fitted to drop yhat into " +
          "the dataset. Click Margins to confirm AME = β for the linear case.",
        command: "predict fitted_values, xb\nmargins",
      },
    ],
  },

  // -----------------------------------------------------------------
  {
    id: "factors-and-interactions",
    title: "Categorical predictors and interactions",
    blurb:
      "Same model with i.education_level and a quadratic in age, then look at " +
      "average marginal effects.",
    steps: [
      {
        title: "Load the data",
        body: "Bundled dataset again.",
        command: 'use "clinic_patients.csv", clear',
        action: { kind: "load_clinic" },
      },
      {
        title: "Open Analyze, OLS form",
        body: "Pick the Regression tab, OLS form.",
        action: { kind: "go_step", step: "analyze" },
      },
      {
        title: "Set outcome and predictors",
        body:
          "Outcome = plaque_index. Predictors = i.education_level (categorical with " +
          "primary as reference), age (you can leave as auto-continuous), brushing_freq.",
        command: "regress plaque_index i.education_level age brushing_freq, vce(robust)",
      },
      {
        title: "Read the level dummies",
        body:
          "Each non-reference education level shows up as its own row in the coefficient " +
          "table (secondary, university, postgrad — primary is the reference). The dot " +
          "tells you which levels differ significantly from primary.",
      },
      {
        title: "Average marginal effects",
        body:
          "Postestimation → Margins (AME). For OLS, AME equals the coefficient for " +
          "main-effect predictors — which is a useful sanity check that the postestimation " +
          "chain is wired correctly.",
        command: "margins",
      },
    ],
  },

  // -----------------------------------------------------------------
  {
    id: "logit-binary",
    title: "Logistic regression for binary outcomes",
    blurb:
      "Predict caries (0/1) from age, smoking, diabetes, and brushing. Read odds " +
      "ratios and average marginal effects.",
    steps: [
      {
        title: "Load the data",
        body: "Bundled dataset.",
        command: 'use "clinic_patients.csv", clear',
        action: { kind: "load_clinic" },
      },
      {
        title: "Switch to the Logistic form",
        body:
          "Analyze → Regression → Logistic. Outcome = caries (a binary 0/1). Add " +
          "predictors age, smoking, diabetes, brushing_freq. Leave 'Odds ratios' on.",
        action: { kind: "go_step", step: "analyze" },
        command: "logistic caries age smoking diabetes brushing_freq",
      },
      {
        title: "Interpret the OR table",
        body:
          "OR > 1 means higher odds of caries. Smoking should land around 3 with a small " +
          "p-value (gold dot). Diabetes and brushing usually trend in the expected " +
          "directions but at the smaller sample size aren't always significant.",
      },
      {
        title: "Average marginal effects",
        body:
          "Postestimation → Margins. For a logit, AME translates the odds-scale effect " +
          "into a percentage-point change in Pr(caries). Smoking AME ≈ +0.08 to +0.12 ⇒ " +
          "smokers are 8–12 percentage points more likely to have caries.",
        command: "margins",
      },
    ],
  },
];
