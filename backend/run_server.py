"""Production entry point — the PyInstaller-bundled binary spawns this.

Electron's prod-mode sidecar boots `solarstata-backend` (the
PyInstaller exe) which runs this script. It reads SOLARSTATA_PORT
from the environment (set by Electron) and starts uvicorn against
solarstata.main:app, binding to 127.0.0.1.

Dev path is unaffected — uvicorn is still invoked directly via
`python -m uvicorn solarstata.main:app` from the .venv.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    port = int(os.environ.get("SOLARSTATA_PORT", "8000"))
    # SOLARSTATA_DESKTOP=1 turns on the singleton-session
    # middleware path; the Electron spawn sets this. Honour the
    # env var here too as a safety net for direct invocations.
    os.environ.setdefault("SOLARSTATA_DESKTOP", "1")

    # Import the app object directly. uvicorn's import-by-string
    # form ("solarstata.main:app") doesn't work inside a frozen
    # PyInstaller bundle because the package import path lives
    # under _MEIPASS rather than on sys.path proper.
    import uvicorn
    from solarstata.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
