# SolarSTATA v3

A point-and-click Stata replica for non-technical researchers — with a Pro mode
for power users. Built to make statistical analysis approachable for dental,
medical, and clinical research without giving up the rigor and reproducibility
of Stata.

> **Status:** Phase 2 (frontend shell with Guided + Pro modes). Statistical
> method coverage expands in Phase 3. See the kickoff brief for the full
> phasing.

## What's in the box

- **Guided mode** — wizard-style: Import → Inspect → Clean →
  Analyze → Visualize → Export. Phase 2 covers Import + Inspect end-to-end;
  no command typing required. Analyze fills in during Phase 3.
- **Pro mode** — 4-pane Stata layout (Variables / Editor / Results / Graphs).
  Phase 2 ships the layout and a syntax-highlighted Monaco placeholder; live
  execution + WebSocket result streaming arrive in Phase 3.
- **One statistical engine** — both modes share the same backend; switching
  modes preserves dataset and `e()` results.
- **Built-in walkthroughs** (Phase 4) — 5 interactive tutorials on a bundled
  synthetic dental dataset.

## Quick start

Requires **Python 3.11+** and **Node 18+**. On macOS/Linux you only need
`python3` on PATH — `make setup` provisions the virtualenv automatically.

```bash
make setup     # one-time: creates .venv and installs backend + frontend deps
make dev       # runs FastAPI on :8000 and Vite on :5173 in parallel
```

Then open http://localhost:5173.

Other useful targets:

```bash
make test            # backend pytest + frontend vitest
make build           # production build of the frontend
make gen-dataset     # regenerate the bundled clinic_patients dataset
make lint            # ruff + mypy + tsc --noEmit
make clean           # remove caches, build artifacts, and .venv
```

If `python3` resolves to a version older than 3.11 (or you want to pin a
specific minor), override the interpreter at setup time:

```bash
make PYTHON=python3.12 setup
```

## Manual setup (without `make`)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e backend[dev]
uvicorn solarstata.main:app --reload --reload-dir backend/src --port 8000

# in another shell
cd frontend && npm install && npm run dev
```

## Project layout

```
backend/                FastAPI + DuckDB + statsmodels stats engine
  src/solarstata/
    api/                HTTP routes
    session/            cookie-based session middleware + in-memory store
    engine/             stats functions + Stata-style formatters + e() store
    io/                 readers/writers (csv, xlsx, dta, parquet)
    walkthroughs/       bundled clinic_patients dataset + walkthrough configs
  tests/                pytest
frontend/               React + TypeScript + Vite + Tailwind (Phase 2+)
archive/v1-v2/          previous Flask implementation, kept for cross-reference
```

## Tech stack (locked)

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Tailwind, Vite |
| Pro editor | Monaco with Stata language definition |
| Backend | FastAPI, Python 3.11+ |
| Data engine | DuckDB in-process + pandas |
| Statistics | statsmodels, linearmodels, scipy |
| File I/O | pyreadstat (.dta), pandas/pyarrow (rest) |
| Graphs | Plotly (server returns JSON, client renders) |
| Session | In-memory, cookie-keyed, 24h idle eviction |

## Development

`make dev` is the fast path. The Vite dev server proxies `/api` and `/healthz`
to FastAPI, so the frontend always talks to the local backend without CORS
plumbing. State (active dataset, mode, selected variable, `e()` results) is
held in an anonymous cookie-keyed session that idles out after 24 h.

## Reference

`stata19_deep_dive.html` (provided separately) is the authoritative spec for
statistical method coverage and engine layering. The older
`Stata: Technical Specification and Operational Logic.rtf` lives in
`archive/v1-v2/` for historical reference only.
