"""Stata-style result containers.

A `Result` is what every engine function returns. It carries:
  - command         :: the Stata command string the user would have typed
  - structured      :: machine-readable payload for the frontend (tables, scalars)
  - text            :: Stata-style ASCII rendering for Pro mode
  - r_update        :: scalars/macros to merge into the session's r() namespace
  - e_update        :: scalars/macros to merge into the session's e() namespace
                       (None for non-estimation commands like summarize)

The `ResultsStore` class mirrors the deep-dive's sketch: it holds the
last estimation's e() so postestimation commands (predict, margins,
test, lincom, estat) can interrogate them. Phase 1 only populates r();
e() arrives in Phase 3 with regression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Result:
    command: str
    structured: dict[str, Any]
    text: str
    r_update: dict[str, Any] = field(default_factory=dict)
    e_update: dict[str, Any] | None = None

    def to_response(self) -> dict[str, Any]:
        """Serialize for the HTTP API."""
        return {
            "command": self.command,
            "result": self.structured,
            "text": self.text,
            "r_set": self.r_update,
            "e_set": self.e_update,
        }


@dataclass
class ResultsStore:
    """Per-session r()/e() namespaces.

    `r()` updates after every command. `e()` only updates after an
    estimation command (regress, logit, etc., Phase 3+) and persists
    until the next estimation overwrites it — that's the contract
    postestimation commands rely on.
    """

    r: dict[str, Any] = field(default_factory=dict)
    e: dict[str, Any] = field(default_factory=dict)

    def apply(self, result: Result) -> None:
        self.r = dict(result.r_update)
        if result.e_update is not None:
            self.e = dict(result.e_update)
