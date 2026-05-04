# SolarSTATA v3

A point-and-click Stata replica for non-technical researchers — with a Pro mode
for power users. Built to make statistical analysis approachable for dental,
medical, and clinical research without giving up the rigor and reproducibility
of Stata.

> **Status:** Phase 1 (backend skeleton). Frontend lands in Phase 2. See the
> kickoff brief for the full phasing.

## What's in the box

- **Guided mode** (Phase 2+) — wizard-style: Import → Inspect → Clean →
  Analyze → Visualize → Export. No command typing required.
- **Pro mode** (Phase 2+) — Monaco editor with Stata syntax, 4-pane layout,
  WebSocket-streamed results.
- **One statistical engine** — both modes share the same backend; switching
  modes preserves dataset and `e()` results.
- **Built-in walkthroughs** (Phase 4) — 5 interactive tutorials on a bundled
  synthetic dental dataset.

## Quick start (Phase 1 backend)

```bash
make dev-backend       # installs deps and runs FastAPI on :8000
make test              # runs the backend test suite
curl http://localhost:8000/healthz
```

Or, without `make`:

```bash
cd backend
pip install -e ".[dev]"
uvicorn solarstata.main:app --reload --port 8000
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

```bash
make dev-backend       # FastAPI auto-reload
make test              # pytest with coverage
make lint              # ruff + mypy (Phase 1.1)
make docker            # build container image
make docker-up         # docker-compose up backend
```

## Reference

`stata19_deep_dive.html` (provided separately) is the authoritative spec for
statistical method coverage and engine layering. The older
`Stata: Technical Specification and Operational Logic.rtf` lives in
`archive/v1-v2/` for historical reference only.
