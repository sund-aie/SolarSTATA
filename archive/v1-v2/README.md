# Archived: SolarSTATA v1 & v2

This directory preserves the Flask-based v1 and v2 codebase for cross-reference
during v3 development. **Nothing here is run, imported, or shipped by v3.**

## What's here

- `app.py` — Flask routes
- `stats_engine.py` — pure-Python statistical engine (scipy/statsmodels wrappers)
- `agent_core.py` — v2's 3-stage Ollama AI pipeline (removed in v3)
- `ai_brain.py` — v1's Ollama wrapper (removed in v3)
- `templates/index.html` — v2 single-page UI
- `static/css/stata.css`, `static/js/app.js` — v2 frontend
- `Stata: Technical Specification and Operational Logic.rtf` — older spec doc;
  `stata19_deep_dive.html` (referenced in v3 kickoff) is the authoritative spec
- `requirements.txt` — original Flask deps

## Why we keep it

`stats_engine.py` is the canonical reference for verifying v3's statistical
math. When implementing OLS, t-tests, ANOVA, etc. in v3, cross-check expected
output against the v1/v2 implementations to catch regressions.

## Original entry point (do not run alongside v3)

```bash
cd archive/v1-v2
pip install -r requirements.txt
python3 app.py  # Flask on http://127.0.0.1:5001
```
