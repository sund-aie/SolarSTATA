"""Stata do-file parser + dispatcher.

The universal Stata command grammar:

    [by varlist:] command [varlist] [if exp] [in range] [, options]

Phase 3 supports the commands needed for OLS/logit/postestimation:
    summarize, tabulate, regress, logit, logistic, predict, margins,
    test, lincom, estat ic, estat vif.

This is intentionally a pragmatic parser: it splits on `if`, `in`, and
the trailing `,` while honouring parentheses inside option arguments. It
does NOT try to be a full Stata lexer (string literals, `;`-terminated
multi-line statements, full abbreviation rules) — those land later if
we need them.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..session.models import Estimation, Frame, Session
from .descriptive import summarize
from .graphs import (
    bar_with_ci as bar_fn,
    box as box_fn,
    histogram as histogram_fn,
    line as line_fn,
    marginsplot as marginsplot_fn,
    residuals_vs_fitted as rvfplot_fn,
    scatter as scatter_fn,
)
from .logit import logit as logit_fn
from .postest import (
    estat_ic as estat_ic_fn,
    estat_vif as estat_vif_fn,
    lincom as lincom_fn,
    margins as margins_fn,
    predict as predict_fn,
    wald_test as wald_test_fn,
)
from .regress import regress as regress_fn
from .results import Result
from .tabulate import tabulate


# ===================================================================
# AST
# ===================================================================

@dataclass
class ParsedCommand:
    raw: str
    prefix: str | None                = None  # 'by' | 'bysort' | None
    prefix_varlist: list[str]         = field(default_factory=list)
    command: str                      = ""
    subcommand: str | None            = None  # for `estat ic` -> subcommand 'ic'
    args: list[str]                   = field(default_factory=list)
    if_expr: str | None               = None
    in_range: str | None              = None
    options: dict[str, str | bool]    = field(default_factory=dict)


# ===================================================================
# Parser
# ===================================================================

_COMMENT_LINE = re.compile(r"^\s*//.*$|^\s*\*.*$")


def parse_line(line: str) -> ParsedCommand | None:
    """Parse a single line. Returns None for empty/comment lines."""
    line = line.rstrip()
    if not line.strip() or _COMMENT_LINE.match(line):
        return None
    # Strip inline `//` comments outside parentheses (rough heuristic).
    line = _strip_inline_comment(line)

    raw = line.strip()
    parsed = ParsedCommand(raw=raw)

    body = raw

    # 1. Prefix (by varlist: / bysort varlist:)
    m = re.match(r"^(bysort|by)\s+([\w\s,]+?)\s*:\s*(.*)$", body)
    if m:
        parsed.prefix = m.group(1)
        parsed.prefix_varlist = [v for v in re.split(r"[\s,]+", m.group(2).strip()) if v]
        body = m.group(3)

    # 2. Comma + options (split at the LAST `,` that's outside any parens)
    body, options_str = _split_options(body)
    if options_str:
        parsed.options = _parse_options(options_str)

    # 3. `in range` (token-level, not inside `if` text)
    body, in_range = _extract_in(body)
    if in_range:
        parsed.in_range = in_range

    # 4. `if expr`
    body, if_expr = _extract_if(body)
    if if_expr:
        parsed.if_expr = if_expr

    # 5. Command + args
    tokens = body.strip().split()
    if not tokens:
        raise ValueError(f"empty command in {raw!r}")
    parsed.command = tokens[0]
    parsed.args = tokens[1:]

    # `estat ic` / `estat vif` — promote first arg to subcommand
    if parsed.command == "estat" and parsed.args:
        parsed.subcommand = parsed.args[0]
        parsed.args = parsed.args[1:]

    return parsed


def _strip_inline_comment(line: str) -> str:
    """Drop a trailing // comment (only if // is preceded by whitespace and outside parens)."""
    depth = 0
    for i, ch in enumerate(line):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            if i == 0 or line[i - 1].isspace():
                return line[:i].rstrip()
    return line


def _split_options(body: str) -> tuple[str, str]:
    """Split body at the last comma that's outside parentheses."""
    depth = 0
    last_comma = -1
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            last_comma = i
    if last_comma < 0:
        return body, ""
    return body[:last_comma].rstrip(), body[last_comma + 1 :].strip()


def _extract_in(body: str) -> tuple[str, str | None]:
    """Pull the trailing `in N/M` qualifier off, if present (paren-aware)."""
    m = re.search(r"\bin\s+([\w\d\-/.]+)\s*$", body)
    if m and _outside_parens(body, m.start()):
        return body[: m.start()].rstrip(), m.group(1).strip()
    return body, None


def _extract_if(body: str) -> tuple[str, str | None]:
    """Pull a trailing `if EXPR` off the body (paren-aware)."""
    m = re.search(r"\bif\b", body)
    if not m:
        return body, None
    # Find the FIRST `if` outside parens. Everything after it (until end) is the expression.
    for match in re.finditer(r"\bif\b", body):
        if _outside_parens(body, match.start()):
            return body[: match.start()].rstrip(), body[match.end() :].strip()
    return body, None


def _outside_parens(s: str, idx: int) -> bool:
    depth = 0
    for ch in s[:idx]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
    return depth == 0


def _parse_options(options_str: str) -> dict[str, str | bool]:
    """Parse the options string after the comma.

    Each option is either:
      name              → True
      name(arg ...)     → "arg ..."
      name=value        → "value"
    Multiple options separated by whitespace.
    """
    out: dict[str, str | bool] = {}
    i = 0
    n = len(options_str)
    while i < n:
        # Skip whitespace
        while i < n and options_str[i].isspace():
            i += 1
        if i >= n:
            break
        # Identifier
        start = i
        while i < n and (options_str[i].isalnum() or options_str[i] == "_"):
            i += 1
        name = options_str[start:i].lower()
        if not name:
            raise ValueError(f"could not parse options near position {i}: {options_str!r}")

        # Check for `(...)`
        if i < n and options_str[i] == "(":
            depth = 1
            i += 1
            arg_start = i
            while i < n and depth > 0:
                if options_str[i] == "(":
                    depth += 1
                elif options_str[i] == ")":
                    depth -= 1
                i += 1
            out[name] = options_str[arg_start : i - 1].strip()
        elif i < n and options_str[i] == "=":
            i += 1
            arg_start = i
            while i < n and not options_str[i].isspace():
                i += 1
            out[name] = options_str[arg_start:i].strip()
        else:
            out[name] = True
    return out


# ===================================================================
# Dispatcher — maps a ParsedCommand to engine functions
# ===================================================================

@dataclass
class DispatchOutcome:
    """One execution emits one or more `Result` blocks plus optional updates
    to the session (estimation record, dataset mutation, command history,
    Plotly figure)."""
    blocks: list[Result] = field(default_factory=list)
    estimation: Estimation | None = None
    dataset_mutations: list[tuple[str, pd.Series]] = field(default_factory=list)
    graphs: list[dict] = field(default_factory=list)


def _graph_result(fig: dict, command: str) -> Result:
    return Result(
        command=command,
        structured={"kind": "graph", "figure": fig},
        text=f"({command} rendered as graph)",
    )


def dispatch(parsed: ParsedCommand, session: Session, frame: Frame) -> DispatchOutcome:
    cmd = parsed.command.lower()

    # Keyword to canonical command (handles short/long forms)
    canonical = {
        "summarize": "summarize", "sum": "summarize", "su": "summarize",
        "tabulate": "tabulate",   "tab": "tabulate",
        "regress":   "regress",   "reg": "regress",
        "logit":     "logit",
        "logistic":  "logit",     # logistic = logit, or  (we set odds_ratios=True)
        "predict":   "predict",
        "margins":   "margins",
        "test":      "test",
        "lincom":    "lincom",
        "estat":     "estat",
        # Phase 5 graph commands
        "histogram": "histogram", "hist": "histogram",
        "scatter":   "scatter",
        "box":       "box",
        "bar":       "bar",
        "line":      "line",
        "rvfplot":   "rvfplot",
        "marginsplot": "marginsplot",
    }.get(cmd, cmd)

    if canonical == "summarize":
        result = summarize(frame.df, parsed.args or None, detail=bool(parsed.options.get("detail")))
        return DispatchOutcome(blocks=[result])

    if canonical == "tabulate":
        if not parsed.args:
            raise ValueError("tabulate requires at least one variable")
        v1 = parsed.args[0]
        v2 = parsed.args[1] if len(parsed.args) > 1 else None
        result = tabulate(frame.df, v1, v2)
        return DispatchOutcome(blocks=[result])

    if canonical == "regress":
        if len(parsed.args) < 2:
            raise ValueError("regress requires depvar and at least one indepvar")
        depvar, *indepvars = parsed.args
        vce, cluster = _parse_vce(parsed.options)
        result, est = regress_fn(
            frame.df, depvar, indepvars,
            vce=vce, cluster=cluster,
            if_expr=parsed.if_expr, in_range=parsed.in_range,
            frame_name=frame.name,
        )
        return DispatchOutcome(blocks=[result], estimation=est)

    if canonical == "logit":
        if len(parsed.args) < 2:
            raise ValueError("logit requires depvar and at least one indepvar")
        depvar, *indepvars = parsed.args
        vce, cluster = _parse_vce(parsed.options)
        odds = bool(parsed.options.get("or")) or cmd == "logistic"
        result, est = logit_fn(
            frame.df, depvar, indepvars,
            odds_ratios=odds, vce=vce, cluster=cluster,
            if_expr=parsed.if_expr, in_range=parsed.in_range,
            frame_name=frame.name,
        )
        return DispatchOutcome(blocks=[result], estimation=est)

    if canonical == "predict":
        if not parsed.args:
            raise ValueError("predict requires a new variable name")
        new_var = parsed.args[0]
        kind = "xb"
        for k in ("xb", "resid", "pr", "stdp"):
            if parsed.options.get(k):
                kind = k
                break
        result, col = predict_fn(frame.df, session.last_estimation, kind=kind, new_var=new_var)
        return DispatchOutcome(blocks=[result], dataset_mutations=[(new_var, col)])

    if canonical == "margins":
        at_means = bool(parsed.options.get("atmeans"))
        result = margins_fn(frame.df, session.last_estimation, at_means=at_means)
        return DispatchOutcome(blocks=[result])

    if canonical == "test":
        result = wald_test_fn(session.last_estimation, parsed.args)
        return DispatchOutcome(blocks=[result])

    if canonical == "lincom":
        result = lincom_fn(session.last_estimation, " ".join(parsed.args))
        return DispatchOutcome(blocks=[result])

    if canonical == "estat":
        sub = (parsed.subcommand or "").lower()
        if sub == "ic":
            result = estat_ic_fn(session.last_estimation)
        elif sub == "vif":
            result = estat_vif_fn(frame.df, session.last_estimation)
        else:
            raise ValueError(f"estat subcommand {sub!r} not supported in Phase 3")
        return DispatchOutcome(blocks=[result])

    # ---- Graphs (Phase 5) ----
    if canonical == "histogram":
        if not parsed.args:
            raise ValueError("histogram requires a variable name")
        bins = int(parsed.options.get("bin") or parsed.options.get("bins") or 20) \
            if not isinstance(parsed.options.get("bin"), bool) else 20
        group = parsed.options.get("by")
        group = group if isinstance(group, str) else None
        fig = histogram_fn(frame.df, parsed.args[0], bins=bins, group=group,
                           value_labels=frame.value_labels)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "scatter":
        if len(parsed.args) < 2:
            raise ValueError("scatter requires y and x (e.g., scatter y x)")
        y_var, x_var = parsed.args[0], parsed.args[1]
        group = parsed.options.get("by")
        group = group if isinstance(group, str) else None
        fig = scatter_fn(frame.df, x_var, y_var, group=group,
                         value_labels=frame.value_labels)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "box":
        if not parsed.args:
            raise ValueError("box requires a variable")
        group = parsed.options.get("over") or parsed.options.get("by")
        group = group if isinstance(group, str) else None
        fig = box_fn(frame.df, parsed.args[0], group=group,
                     value_labels=frame.value_labels)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "bar":
        if not parsed.args:
            raise ValueError("bar requires a variable")
        group = parsed.options.get("over") or parsed.options.get("by")
        group = group if isinstance(group, str) else None
        fig = bar_fn(frame.df, parsed.args[0], group=group,
                     value_labels=frame.value_labels)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "line":
        if len(parsed.args) < 2:
            raise ValueError("line requires y and x (e.g., line y x)")
        y_var, x_var = parsed.args[0], parsed.args[1]
        group = parsed.options.get("by")
        group = group if isinstance(group, str) else None
        fig = line_fn(frame.df, x_var, y_var, group=group,
                      value_labels=frame.value_labels)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "rvfplot":
        fig = rvfplot_fn(frame.df, session.last_estimation)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    if canonical == "marginsplot":
        if session.last_estimation is None:
            raise ValueError("no estimates stored — run regress or logit first")
        m = margins_fn(frame.df, session.last_estimation, at_means=False)
        fig = marginsplot_fn(m.structured)
        return DispatchOutcome(
            blocks=[_graph_result(fig, parsed.raw)],
            graphs=[fig],
        )

    raise ValueError(f"command {cmd!r} not supported in Phase 5")


def _parse_vce(options: dict[str, str | bool]) -> tuple[str, str | None]:
    """Parse `vce(robust)` / `vce(hc3)` / `vce(cluster id)` into (vce_kind, cluster_var).

    Also accepts the bare `robust` shorthand (Stata canonical alias for vce(robust)).
    """
    if options.get("robust"):
        return "robust", None
    raw = options.get("vce")
    if raw is None or raw is True:
        return "ols", None
    raw = str(raw).strip()
    if raw == "robust":
        return "robust", None
    if raw == "hc3":
        return "hc3", None
    if raw.startswith("cluster"):
        # vce(cluster id)
        parts = raw.split()
        if len(parts) < 2:
            raise ValueError("vce(cluster ...) requires a cluster variable name")
        return "cluster", parts[1]
    raise ValueError(f"unknown vce specification: {raw!r}")
