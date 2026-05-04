"""Session data model.

A Session owns multiple Frames (Stata calls them frames; each frame is a
named dataset that coexists in memory). The current frame is the one
commands operate on by default; later phases will expose frame switching
via `frame change`.

Each Session also tracks `e()` and `r()` results plus a command history
for the do-file log (Phase 3+).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class Frame:
    """A named in-memory dataset plus Stata-style metadata.

    `df` is the source of truth. `column_labels` and `value_labels` are
    populated when reading .dta files via pyreadstat; CSV/XLSX uploads
    leave them empty. `storage_types` mimics Stata's byte/int/long/
    float/double/str distinction (set by `compress`-style autotyping in
    Phase 1.1; for now we just record the pandas dtype).
    """

    name: str
    df: pd.DataFrame
    column_labels: dict[str, str] = field(default_factory=dict)
    value_labels: dict[str, dict[Any, str]] = field(default_factory=dict)
    storage_types: dict[str, str] = field(default_factory=dict)
    source_filename: str | None = None

    @property
    def n_obs(self) -> int:
        return len(self.df)

    @property
    def n_vars(self) -> int:
        return self.df.shape[1]


@dataclass
class Session:
    """Per-cookie session state.

    Anonymous, ephemeral. Evicted after `idle_timeout_seconds` of
    inactivity. Holds frames, e()/r() results, and command history.
    """

    session_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    frames: dict[str, Frame] = field(default_factory=dict)
    current_frame_name: str = "default"

    e_results: dict[str, Any] = field(default_factory=dict)
    r_results: dict[str, Any] = field(default_factory=dict)

    command_history: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.last_activity = time.time()

    @property
    def current_frame(self) -> Frame | None:
        return self.frames.get(self.current_frame_name)

    def set_frame(self, frame: Frame, *, make_current: bool = True) -> None:
        self.frames[frame.name] = frame
        if make_current:
            self.current_frame_name = frame.name

    def append_history(self, command: str) -> None:
        self.command_history.append(command)
