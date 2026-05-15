# SolarSTATA v3

A point-and-click Stata replica for researchers — with a Pro mode for power
users. Built to make statistical analysis approachable for dental, medical, and
clinical research without giving up the rigor and reproducibility of Stata.

> **Status:** v3.0.2 — clinical-research polish. Adds the ANOVA family
> (one-way with Bartlett + Bonferroni/Scheffé/Sidak posthoc, two-way,
> repeated-measures with sphericity corrections), normality / equal-variance
> diagnostics (Shapiro-Wilk, Levene), `tabstat` by-group descriptives,
> grouped bar charts, and a postest-actions row under every estimation card.

![Guided mode hero — clinic_patients.csv loaded with an OLS regression result.](docs/screenshots/guided.png)
> _Screenshot placeholder — generate with `make screenshots` once the
> playwright capture script lands (v3.0.1)._

## What's in the box

- **Guided mode** — wizard-style: Import → Inspect → Clean → Analyze →
  Visualize → Export. Drag-and-drop import (with sheet + header-row pickers
  for messy Excel), descriptive cards, OLS / logit + postestimation forms,
  6 Plotly chart types, dataset + do-file + PDF report exports. No command
  typing required.
- **Pro mode** — 4-pane Stata layout: Variables / Editor / Results / Graphs.
  Monaco editor with a custom Stata language (factor variables, options,
  variable autocomplete), live WebSocket-streamed results, command history
  on ArrowUp.
- **One statistical engine** — both modes share the same FastAPI backend;
  switching modes preserves dataset, `e()` results, and command history.
- **5 built-in walkthroughs** on a bundled synthetic dental dataset
  (`clinic_patients.csv` — 400 fictional patients with realistic
  correlations baked in plus 6 dirty rows for cleaning practice).
- **Light / dark mode**, persisted to localStorage. Plotly figures swap
  templates automatically.
- **Workspace persistence** — download your dataset + `e()` + command
  history as a single JSON; re-upload to restore on any machine.

![Pro mode — Monaco editor, WebSocket-streamed Stata output, live Plotly graphs.](docs/screenshots/pro.png)

## One-click launchers

### macOS

1. Download or clone the repo.
2. **Double-click `solarstata.command`** in Finder.

On the first run the launcher provisions `.venv` and `node_modules`
(takes ~1 minute). Subsequent launches boot the app in under 5 seconds and
open `http://localhost:5173` in your browser.

> If macOS Gatekeeper blocks the launcher, right-click → Open the first
> time. Close the Terminal window or press Ctrl+C to stop both servers.

> If double-clicking does nothing because the executable bit was stripped
> during checkout (a GitHub Contents API quirk that will be fixed in
> v3.0.1), open Terminal in the repo folder and run once:
> `chmod +x solarstata.command`

### Windows

1. Download or clone the repo.
2. **Double-click `solarstata.bat`** in Explorer.

The launcher opens two PowerShell windows (backend + frontend) and then
your browser. Close either window to stop the corresponding server.

### Either OS — manual

Requires **Python 3.11+** and **Node 18+**.

```bash
make setup     # one-time: creates .venv, installs backend + frontend deps
make dev       # runs FastAPI on :8000 and Vite on :5173 in parallel
```

If `python3` resolves to a version older than 3.11:

```bash
make PYTHON=python3.12 setup
```

## 60-second quickstart

1. **Boot** — double-click the launcher (or `make dev`).
2. **Import** — drag `backend/src/solarstata/walkthroughs/datasets/clinic_patients.csv`
   into the dropzone. (Or click the "Load the bundled dataset" button in
   any walkthrough.)
3. **Inspect** — click `plaque_index`, hit **Run summarize**. Watch for the
   warm-orange missing-% badges on `plaque_index`, `gingival_index`, and
   `brushing_freq`.
4. **Analyze** — switch to the Analyze step → Regression → OLS. Set
   outcome = `plaque_index`, add `age`, `i.sex`, `brushing_freq`, tick
   **Robust SE**. **Run regression**. Note the gold dot next to
   `brushing_freq` (p < 0.05).
5. **Visualize** — Visualize step → Histogram of `plaque_index`. Click
   **Render chart**.
6. **Export** — Export step → **PDF**. You'll get a clean research
   report of everything you just did.

Or for the same thing in Pro mode:

```stata
use "clinic_patients.csv", clear
regress plaque_index age i.sex brushing_freq, vce(robust)
margins
predict yhat
histogram plaque_index
```

## Project layout

```
backend/                FastAPI + DuckDB + statsmodels stats engine
  src/solarstata/
    api/                HTTP routes (data, stats, graphs, export, workspace, ws)
    session/            cookie-based session middleware + in-memory store
    engine/             stats functions, graphs, formatters, factor expansion
    io/                 readers/writers (csv, xlsx, dta, parquet)
    walkthroughs/       bundled clinic_patients dataset + walkthrough configs
  tests/                pytest
frontend/               React + TypeScript + Vite + Tailwind + Monaco + Plotly
solarstata.command      macOS launcher (double-click)
solarstata.bat          Windows launcher (double-click)
archive/v1-v2/          previous Flask implementation, kept for cross-reference
```

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Tailwind, Vite |
| Pro editor | Monaco with custom Stata language |
| Charts | Plotly (server returns JSON, react-plotly.js renders) |
| Backend | FastAPI, Python 3.11+ |
| Stats | statsmodels, scipy, statsmodels postestimation |
| File I/O | pyreadstat (.dta), pandas/pyarrow (rest) |
| PDF | WeasyPrint |
| Session | Anonymous cookie, in-memory, 24h idle eviction |

## Statistical methods

Every SolarSTATA Pro command maps to the same statsmodels/scipy routine
that real Stata wraps. The table below is the canonical cross-reference
between what you'd type in StataCorp's Stata and what SolarSTATA runs
under the hood:

| Real Stata | SolarSTATA Pro | Engine | Notes |
|---|---|---|---|
| `summarize y, detail` | `summarize y, detail` | pandas + scipy | mean, sd, percentiles, skew, kurtosis |
| `tabulate x` / `tabulate x y` | `tabulate x` / `tabulate x y` | pandas crosstab + scipy chi² | one- and two-way frequency tables |
| `tabstat y, by(g) stats(n mean sd)` | `tabstat y, by(g) stats(n mean sd)` | pandas groupby.agg | by-group descriptives matrix |
| `oneway y g` | `oneway y g` | scipy.stats.f_oneway + Bartlett | always emits Bartlett's test |
| `oneway y g, bonferroni` | `oneway y g, bonferroni` | scipy + pooled-SE pairwise | Bonferroni / Scheffé / Sidak posthoc |
| `anova y a##b` | `anova y a##b` | statsmodels OLS + Type-II ANOVA | two-way with interaction |
| `anova y subj##time, repeated(time)` | `anova y subj##time, repeated(time) gg` | statsmodels.AnovaRM + GG/HF ε | repeated-measures with sphericity correction; mixed between×within lands in v3.1 |
| `swilk y` | `swilk y` | scipy.stats.shapiro | Shapiro-Wilk normality, optional by-group |
| `robvar y, by(g)` | `robvar y, by(g)` | scipy.stats.levene | Levene's equal-variance test |
| `regress y x1 x2, vce(robust)` | `regress y x1 x2, vce(robust)` | statsmodels OLS + HC0–HC3 / cluster | full OLS with robust / clustered SE |
| `logit y x1 x2, or` | `logit y x1 x2, or` | statsmodels Logit | with odds-ratios, robust SE, postest |
| `margins`, `predict`, `test` | `margins`, `predict`, `test` | statsmodels postest | available under every estimation card |

### Which test do I run?

A short decision tree for the most common clinical-research questions:

```
Two-group comparison
├── Continuous outcome
│   ├── Normal (swilk p > 0.05)?            → t-test (v3.1)
│   └── Skewed?                              → Mann-Whitney (v3.1)
└── Categorical outcome                      → chi² via tabulate x y

Three+ groups, continuous outcome
├── Independent, normal, equal variances     → oneway (Bartlett built-in)
├── Independent, normal, unequal variances   → oneway then check Bartlett's p
├── Independent, non-normal                  → Kruskal-Wallis (v3.1)
└── Repeated measures (within-subject)       → anova_rm with gg correction

Two factors, continuous outcome              → anova y a##b
Continuous predictor + continuous outcome    → regress
Binary outcome                                → logit (with or for odds-ratios)
```

If unsure about normality, run **swilk** first; if Shapiro rejects
(p < 0.05) and you'd reach for ANOVA, default to the non-parametric
equivalent (Kruskal-Wallis / Friedman lands in v3.1).

## About the bundled dataset

`clinic_patients.csv` is **synthetic** — 400 fictional patients generated
deterministically (seed = 1985, StataCorp's founding year) plus 6
obviously dirty rows with `patient_id ≥ 9000` for the cleaning
walkthrough. Realistic correlations are baked in: smoking → more
periodontal pocket depth, more brushing → less plaque, higher education
→ more brushing, age → more pocket depth, diabetes → higher gingival
index.

**Use it for learning, demos, and bug reports. Do not use it as a real
research dataset.** To load your own data, drag any `.csv`, `.xlsx`,
`.dta`, or `.parquet` file (up to 50 MB) into the import dropzone.
Multi-sheet workbooks get an explicit sheet picker; sheets with title /
subtitle rows above the headers get a header-row picker.

## Development

```bash
make dev             # backend (8000) + frontend (5173) in parallel
make test            # backend pytest + frontend vitest
make build           # production build of the frontend
make gen-dataset     # regenerate the bundled clinic_patients dataset
make lint            # ruff + mypy + tsc --noEmit
make clean           # remove caches and .venv
```

Vite proxies `/api` and `/healthz` to FastAPI on 8000, so the frontend
always talks to the local backend without CORS plumbing. State (active
dataset, mode, selected variable, `e()` results, command history) lives
in an anonymous cookie-keyed session that idles out after 24 h.

## Out of scope for v3.0

The following land in v3.1+ — important but not blocking the ship:

- Tier 2 stats: survival (Cox, KM), panel (`xtreg`), mixed-effects, IV.
- Diagnostic-first messy-data importer (the staged upload + sheet
  picker handle most cases today; deeper data-quality diagnostics
  arrive in v3.1).
- Walkthrough #2 (Clean and recode): lands when `drop`, `recode`,
  `generate`, `egen`, and `label` ship in Phase 4.1.
- Multi-user / login.
- AI / LLM integration (deliberately out of scope; the engine is
  fully transparent and reproducible).

## Reference

`docs/stata19_deep_dive.html` is the authoritative spec for statistical
method coverage and engine layering. The older
`Stata: Technical Specification and Operational Logic.rtf` lives in
`archive/v1-v2/` for historical reference only.
