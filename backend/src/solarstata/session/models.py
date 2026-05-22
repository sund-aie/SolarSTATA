"""Session data model.

A Session owns multiple Frames (Stata calls them frames; each frame is a
named dataset that coexists in memory). The current frame is the one
commands operate on by default; later phases will expose frame switching
via `frame change`.

Each Session also tracks `e()` and `r()` results plus a command history
for the do-file log. Phase 3 adds `last_estimation` — the in-memory
fitted model object that postestimation commands (predict, margins,
test, lincom, estat) need to interrogate. It's intentionally not part
of `e()` because statsmodels result objects don't survive JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class Estimation:
    """In-memory record of the most recent estimation.

    `model` is whatever the engine function chose to stash for postest
    (typically a statsmodels Results object). `design_columns` is the
    list of coefficient names in their final post-factor-expansion order.
    `frame_name` records which frame the model was fit on so postestimation
    can refuse to operate against the wrong dataset.
    """

    command: str
    cmd_kind: str                            # 'regress', 'logit', etc.
    depvar: str
    indepvars: list[str]                     # raw input tokens (incl. factor notation)
    design_columns: list[str]                # expanded coefficient names
    frame_name: str
    n_obs: int
    if_expr: str | None = None               # qualifier used at fit time
    in_range: str | None = None              # qualifier used at fit time
    cluster: str | None = None
    model: Any = None                        # statsmodels fitted result
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StagedUpload:
    """A file the user has uploaded but hasn't fully materialized yet.

    Multi-sheet Excel uploads land here first so the user can pick a sheet
    and a header row before the dataset is parsed and committed to a Frame.
    The temp file lives on disk under `path` and is cleaned up on finalize
    or session eviction.
    """

    file_id: str
    path: str
    original_filename: str
    format: str
    sheets: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


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
    last_estimation: Estimation | None = None

    # NOTE: staged uploads (the intermediate state of the xlsx
    # picker flow) live in a process-wide store now —
    # solarstata.session.staging — keyed by file_id alone. This
    # makes the upload→finalize handshake robust under the
    # Electron desktop shell, where cross-host cookies don't ride
    # along reliably.

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
