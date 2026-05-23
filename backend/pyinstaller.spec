# PyInstaller spec for the SolarSTATA backend.
#
# Produces a ONE-FOLDER bundle at dist/solarstata-backend/
# containing the Python interpreter, the scientific stack, and
# all of solarstata's source. The Electron shell spawns the
# launcher binary inside that folder (dist/solarstata-backend/
# solarstata-backend{,.exe}) for production builds.
#
# Why one-folder (not one-file): one-file unpacks every dependency
# to a temp dir on each launch, which is unacceptable for a ~200MB
# scientific Python bundle. One-folder boots in seconds.
#
# Build:  python -m PyInstaller backend/pyinstaller.spec --clean
# Output: dist/solarstata-backend/solarstata-backend  (the runner)

# ruff: noqa: F821 — Analysis/EXE/COLLECT are PyInstaller magic.
# mypy: ignore-errors

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
)

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).resolve()  # backend/
SRC_ROOT = PROJECT_ROOT / "src"

# Hidden imports — packages PyInstaller's static analysis can miss
# because they're imported via strings or only at runtime.
hidden = [
    # Uvicorn / Starlette / FastAPI plumbing
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    "wsproto",
    "h11",
    "httptools",
    "anyio",
    "asgiref",

    # Pydantic v2 internals + extras
    "pydantic",
    "pydantic_core",
    "pydantic_settings",

    # Multipart upload
    "python_multipart",
    "multipart",

    # Data / scientific stack
    "pandas",
    "pandas._libs.tslibs.base",
    "pandas._libs.tslibs.timezones",
    "numpy",
    "pyarrow",
    "openpyxl",
    "pyreadstat",
    "scipy",
    "scipy.stats",
    "scipy.special",
    "scipy._lib.messagestream",
    "statsmodels",
    "statsmodels.api",
    "statsmodels.tsa",
    "statsmodels.tools",
    "statsmodels.stats.anova",
    "statsmodels.stats.multicomp",
    "statsmodels.formula.api",

    # Templating + rendering
    "jinja2",
    "plotly",
    "plotly.io",
    "plotly.graph_objs",

    # Itsdangerous (session cookies)
    "itsdangerous",

    # DuckDB (optional but listed in deps)
    "duckdb",
]

# Pull in every submodule of these big packages — the static
# analyzer routinely misses sub-modules referenced via __import__.
for pkg in (
    "uvicorn", "scipy", "statsmodels", "pandas", "plotly",
    "pyarrow", "openpyxl", "pydantic_core",
):
    hidden.extend(collect_submodules(pkg))

# Data files — package data that ships next to .py modules.
# Format: (source-on-disk, dest-relative-to-bundle-root)
datas = [
    # Bundled walkthrough dataset (Path(__file__).parent in
    # walkthroughs.datasets resolves to whichever path the package
    # is installed at — PyInstaller flattens onto _internal/<pkg>).
    (str(SRC_ROOT / "solarstata" / "walkthroughs" / "datasets" / "clinic_patients.csv"),
     "solarstata/walkthroughs/datasets"),
    (str(SRC_ROOT / "solarstata" / "walkthroughs" / "datasets" / "clinic_patients.dta"),
     "solarstata/walkthroughs/datasets"),
]

# Pull in package data the scientific stack ships internally:
# scipy needs LAPACK/BLAS extension data, statsmodels needs its
# tabulated datasets, plotly needs its JS/templates registry.
for pkg in ("scipy", "statsmodels", "plotly", "pyarrow"):
    try:
        datas.extend(collect_data_files(pkg))
    except Exception:  # noqa: BLE001 — best-effort
        pass


a = Analysis(
    [str(PROJECT_ROOT / "run_server.py")],
    pathex=[str(SRC_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # WeasyPrint's optional GTK dependency is intentionally
        # left out — it requires GTK system libs that we don't
        # bundle. The backend probes at startup and reports PDF
        # unavailable; the user falls back to HTML export.
        # We do NOT exclude weasyprint itself — the module import
        # must succeed for the probe to run; only PDF rendering
        # fails (degraded path).

        # Tk-based pyplot backend we never use, saves ~30MB.
        "tkinter",
        "matplotlib.tests",
        "scipy.tests",
        "statsmodels.tests",
        "pandas.tests",
        "numpy.tests",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="solarstata-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # so stdout/stderr go to Electron's log pipe
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="solarstata-backend",  # → dist/solarstata-backend/
)
