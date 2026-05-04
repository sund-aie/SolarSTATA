# SolarSTATA v3 — Backend

FastAPI + DuckDB + statsmodels. Phase 1 covers data import, summarize,
tabulate, and the session model. Regression and the do-file parser come in
later phases.

## Install & run

```bash
pip install -e ".[dev]"
uvicorn solarstata.main:app --reload --port 8000
```

## Test

```bash
pytest -v
```

## Layout

```
src/solarstata/
  api/             HTTP routes (health, data, stats)
  session/         cookie-based session middleware + in-memory store
  engine/          stats functions + Stata-style formatters + e()/r() store
  io/              readers/writers (csv, xlsx, dta, parquet)
  walkthroughs/    bundled clinic_patients dataset + generator
tests/             pytest suite
```

## Endpoints (Phase 1)

| Method | Path | Description |
|---|---|---|
| GET  | `/healthz`            | Liveness/version probe |
| POST | `/api/upload`         | Multipart upload of a dataset (csv/xlsx/dta/parquet) |
| GET  | `/api/data/preview`   | First N rows of the active frame |
| GET  | `/api/data/columns`   | Column metadata for the active frame |
| POST | `/api/stats/summarize`| Stata `summarize [, detail]` |
| POST | `/api/stats/tabulate` | Stata `tabulate var1 [var2]` |
