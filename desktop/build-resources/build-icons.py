"""Pre-render the .icns and .ico from icon.svg.

This is a one-shot build helper, not a project dependency.
Run it whenever the master SVG changes; commit the resulting
binaries alongside the SVG so production builds (electron-builder
dist:mac / dist:win) pick them up without any rasterization
toolchain on the build host.

Tools used (pip install cairosvg pillow):
  cairosvg → SVG to PNG at arbitrary size
  Pillow   → write .icns (IcnsImagePlugin) and .ico (IcoImagePlugin)
             with the canonical multi-resolution size sets.
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image


HERE = Path(__file__).resolve().parent
SVG = HERE / "icon.svg"
ICNS = HERE / "icon.icns"
ICO = HERE / "icon.ico"

# .icns canonical sizes (Apple). Pillow's IcnsImagePlugin picks
# matching ic** members from this set.
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]

# .ico canonical sizes (Windows). 256 is the modern installer header.
ICO_SIZES = [16, 32, 48, 64, 128, 256]


def rasterize(size: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(
        url=str(SVG),
        output_width=size,
        output_height=size,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def build_icns() -> None:
    base = rasterize(1024)
    sizes_pillow = [(s, s) for s in ICNS_SIZES]
    base.save(ICNS, format="ICNS", append_images=[], sizes=sizes_pillow)
    print(f"wrote {ICNS} ({ICNS.stat().st_size:,} bytes)")


def build_ico() -> None:
    # Pillow downscales the base image to each requested size; use
    # the largest target (256) as the source so the small sizes are
    # supersampled, not upscaled from a tiny source.
    base = rasterize(256)
    sizes_pillow = [(s, s) for s in ICO_SIZES]
    base.save(ICO, format="ICO", sizes=sizes_pillow)
    print(f"wrote {ICO} ({ICO.stat().st_size:,} bytes)")


if __name__ == "__main__":
    if not SVG.exists():
        raise SystemExit(f"missing master: {SVG}")
    build_icns()
    build_ico()
