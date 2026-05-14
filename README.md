# SolarSTATA v3

A point-and-click Stata replica for researchers — with a Pro mode for power
users. Built to make statistical analysis approachable for dental, medical, and
clinical research without giving up the rigor and reproducibility of Stata.

> **Status:** Phase 5 (final shipping surface — graphs, exports, launchers,
> light mode). v3.0 RC.

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
