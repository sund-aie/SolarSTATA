"""Export routes: dataset (csv / xlsx / dta / parquet), do-file, and a
research-report PDF/HTML rendered from the session's command history.
"""

from __future__ import annotations

import io
import tempfile
from datetime import datetime
from pathlib import Path

import pyreadstat
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jinja2 import Template

from ..session.models import Session
from .deps import get_session

router = APIRouter(prefix="/export", tags=["export"])


# ===================================================================
# Dataset
# ===================================================================

@router.get("/dataset")
def export_dataset(
    format: str = Query("csv", pattern="^(csv|xlsx|dta|parquet)$"),
    frame: str = Query("default"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    f = _require_frame(session, frame)
    df = f.df
    stem = Path(f.source_filename or "dataset").stem

    if format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        body = buf.getvalue().encode("utf-8")
        return _stream(body, f"{stem}.csv", "text/csv")
    if format == "xlsx":
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        return _stream(buf.getvalue(), f"{stem}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if format == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return _stream(buf.getvalue(), f"{stem}.parquet", "application/octet-stream")
    if format == "dta":
        # pyreadstat writes to a path; round-trip through a temp file.
        with tempfile.NamedTemporaryFile(suffix=".dta", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            pyreadstat.write_dta(
                df,
                str(tmp_path),
                column_labels=[f.column_labels.get(c, "") for c in df.columns]
                if f.column_labels else None,
                variable_value_labels=f.value_labels or None,
            )
            body = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        return _stream(body, f"{stem}.dta", "application/x-stata-dta")
    raise HTTPException(status_code=400, detail=f"Unknown format: {format}")


# ===================================================================
# Do-file
# ===================================================================

@router.get("/dofile")
def export_dofile(session: Session = Depends(get_session)) -> StreamingResponse:
    lines = [
        "* SolarSTATA — exported do-file",
        f"* Generated: {datetime.utcnow().isoformat()}Z",
        "* Every action you took this session, in order.",
        "",
    ]
    lines.extend(session.command_history or ["* (no commands recorded)"])
    body = "\n".join(lines).encode("utf-8")
    return _stream(body, "session.do", "text/plain")


# ===================================================================
# Report (PDF / HTML)
# ===================================================================

_REPORT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SolarSTATA report</title>
  <style>
    @page { size: A4; margin: 24mm 18mm; }
    body {
      font-family: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif;
      color: #1F1B14;
      line-height: 1.55;
      font-size: 11pt;
    }
    h1, h2, h3 {
      font-family: 'Instrument Serif', Georgia, serif;
      font-weight: normal;
      color: #1F1B14;
      letter-spacing: -0.01em;
    }
    h1 { font-size: 28pt; margin: 0 0 4pt; }
    h2 { font-size: 18pt; margin: 24pt 0 6pt; border-bottom: 1px solid #D6CFC0; padding-bottom: 4pt; }
    h3 { font-size: 13pt; margin: 16pt 0 4pt; font-style: italic; color: #B89548; }
    .subtitle { color: #8A8270; font-size: 10pt; margin-bottom: 18pt; }
    .meta { color: #8A8270; font-size: 9pt; margin-bottom: 28pt; }
    pre.command {
      background: #F4F1E9;
      border: 1px solid #D6CFC0;
      border-left: 3px solid #B89548;
      padding: 8pt 10pt;
      font-family: 'IBM Plex Mono', 'Menlo', monospace;
      font-size: 9pt;
      color: #1F1B14;
      white-space: pre-wrap;
      word-break: break-word;
      margin: 6pt 0 10pt;
    }
    pre.output {
      background: #FBF9F4;
      border: 1px solid #D6CFC0;
      padding: 10pt 12pt;
      font-family: 'IBM Plex Mono', 'Menlo', monospace;
      font-size: 8.5pt;
      color: #1F1B14;
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0 0 12pt;
    }
    .footer { color: #8A8270; font-size: 8pt; margin-top: 36pt; text-align: center; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <div class="subtitle">SolarSTATA session report</div>
  <div class="meta">
    Generated {{ generated_at }} ·
    Dataset: <strong>{{ dataset or "(none)" }}</strong> ·
    {{ n_commands }} commands run
  </div>

  {% if not entries %}
  <p style="color: #8A8270; font-style: italic;">
    No commands have been run in this session yet. Run summarize, regress, or any
    other command, then export again.
  </p>
  {% endif %}

  {% for entry in entries %}
  <h3>{{ loop.index }}. {{ entry.title }}</h3>
  <pre class="command">{{ entry.command }}</pre>
  {% if entry.text %}
  <pre class="output">{{ entry.text }}</pre>
  {% endif %}
  {% endfor %}

  <div class="footer">
    SolarSTATA v3 · {{ generated_at }}
  </div>
</body>
</html>
"""


def _render_report_html(session: Session) -> str:
    history = session.command_history or []
    entries = [{
        "title": _entry_title(cmd),
        "command": cmd,
        "text": "",          # Output text isn't archived per-command in
                             # the Phase-1 session model. Pro mode users
                             # see streamed output live; the report is a
                             # command-by-command audit for now.
    } for cmd in history]

    frame = session.current_frame
    dataset = frame.source_filename if frame else None

    return Template(_REPORT_HTML).render(
        title="Research report",
        subtitle="SolarSTATA session export",
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        dataset=dataset,
        n_commands=len(history),
        entries=entries,
    )


def _entry_title(cmd: str) -> str:
    head = cmd.strip().split()[0] if cmd.strip() else "(blank)"
    titles = {
        "use": "Load dataset",
        "summarize": "Descriptive statistics",
        "tabulate": "Frequency table",
        "regress": "Linear regression",
        "logit": "Logistic regression",
        "logistic": "Logistic regression",
        "predict": "Predict",
        "margins": "Average marginal effects",
        "test": "Wald test",
        "lincom": "Linear combination",
        "estat": "Estimation diagnostics",
        "histogram": "Histogram",
        "scatter": "Scatter plot",
        "box": "Box plot",
        "bar": "Bar chart",
        "line": "Line chart",
        "rvfplot": "Residuals vs fitted",
        "marginsplot": "Marginsplot",
    }
    return titles.get(head, head.capitalize())


@router.get("/report")
def export_report(
    format: str = Query("pdf", pattern="^(pdf|html)$"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    html = _render_report_html(session)
    if format == "html":
        return _stream(html.encode("utf-8"), "solarstata_report.html", "text/html")

    try:
        from weasyprint import HTML
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PDF export unavailable: {exc}")

    pdf_bytes = HTML(string=html).write_pdf()
    return _stream(pdf_bytes, "solarstata_report.pdf", "application/pdf")


# ===================================================================
# Helpers
# ===================================================================

def _require_frame(session: Session, name: str):
    frame = session.frames.get(name)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {name}")
    return frame


def _stream(body: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(body),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
