"""Process-wide staged-uploads store.

A staged upload is the intermediate state between accepting a
multi-sheet .xlsx file and committing one of its sheets to a frame.
The user picks a sheet + header row through the UI; the finalize
route then parses the file with those choices.

Historical note: before v3.1 this lived on the `Session` dataclass
keyed by cookie-bound session id. That broke under the Electron
desktop shell, where the renderer (http://localhost:5173) and the
sidecar (http://127.0.0.1:<dynamic>) are different hosts, so the
session cookie set by the upload response never rode along on the
follow-up finalize POST. The result was a deterministic 404 at
finalize-time even though staging succeeded.

The fix is to key by `file_id` alone — a server-generated UUID
(uuid.uuid4().hex) is unguessable, and this is a single-user
desktop app where cross-session isolation buys nothing.

Thread-safe via an RLock so concurrent finalize attempts pop
exactly once.
"""

from __future__ import annotations

import threading
from typing import Iterable

from .models import StagedUpload


_staged: dict[str, StagedUpload] = {}
_lock = threading.RLock()


def put(staged: StagedUpload) -> None:
    """Insert (or replace) a staged upload."""
    with _lock:
        _staged[staged.file_id] = staged


def get(file_id: str) -> StagedUpload | None:
    """Return the staged upload for `file_id`, or None if absent."""
    with _lock:
        return _staged.get(file_id)


def pop(file_id: str) -> StagedUpload | None:
    """Remove and return the staged upload for `file_id`."""
    with _lock:
        return _staged.pop(file_id, None)


def all_ids() -> list[str]:
    """Snapshot of currently staged file_ids — useful for diagnostics."""
    with _lock:
        return list(_staged.keys())


def clear(ids: Iterable[str] | None = None) -> None:
    """Test helper: remove all entries, or only the given ids."""
    with _lock:
        if ids is None:
            _staged.clear()
        else:
            for i in ids:
                _staged.pop(i, None)
