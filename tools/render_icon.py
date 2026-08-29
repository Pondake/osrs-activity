"""Rasterise assets/icon.svg into the PNGs Home Assistant and GitHub want.

Not a general SVG renderer, and it does not pretend to be one. The icon is a
grid of rounded rectangles plus one blurred copy of itself, which is exactly
the subset that can be reproduced faithfully with Pillow and nothing else --
no cairo, no headless browser, no system packages.

    python tools/render_icon.py

Rendered at 4x and downsampled, because the corner radius is 3.2px on a 26.7px
tile and that only survives with supersampling.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SVG_NS = "{http://www.w3.org/2000/svg}"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "icon.svg"

# name -> edge length. 256 and 512 are what the Home Assistant brands
# repository asks for; 1024 is a comfortable size for a GitHub social preview
# to be cropped from.
BRAND = ROOT / "custom_components" / "osrs_activity" / "brand"
OUTPUTS = {
    # brand/ is where both Home Assistant and HACS look for a custom
    # integration's own icons. Since 2026.3 the frontend serves these through a
    # local proxy and they take priority over the brands CDN, so no submission
    # to home-assistant/brands is needed -- that repository stopped accepting
    # custom integrations for exactly this reason.
    BRAND / "icon.png": 256,
    BRAND / "icon@2x.png": 512,
    ROOT / "assets" / "icon-256.png": 256,
    # A comfortable size to crop a GitHub social preview from.
    ROOT / "assets" / "icon-1024.png": 1024,
}

SUPERSAMPLE = 4


def _colour(value: str | None, opacity: float) -> tuple[int, int, int, int] | None:
    """#rrggbb plus an opacity into an RGBA tuple."""
    if not value or value == "none":
        return None
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return red, green, blue, max(0, min(255, round(opacity * 255)))


def _rects(group: ET.Element) -> list[tuple[list[float], tuple, float]]:
    out = []
    for rect in group.iter(f"{SVG_NS}rect"):
        opacity = float(rect.get("fill-opacity", 1))
        fill = _colour(rect.get("fill"), opacity)
        if fill is None:
            continue
        x, y = float(rect.get("x", 0)), float(rect.get("y", 0))
        box = [x, y, x + float(rect.get("width", 0)), y + float(rect.get("height", 0))]
        out.append((box, fill, float(rect.get("rx", 0))))
    return out


def _draw(size: int, scale: float, rects) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for box, fill, radius in rects:
        scaled = [value * scale for value in box]
        if radius > 0:
            pen.rounded_rectangle(scaled, radius=radius * scale, fill=fill)
        else:
            pen.rectangle(scaled, fill=fill)
    return layer


def _blur_radius(root: ET.Element) -> float:
    for blur in root.iter(f"{SVG_NS}feGaussianBlur"):
        return float(blur.get("stdDeviation", 0))
    return 0.0


def render(source: Path, edge: int) -> Image.Image:
    tree = ET.parse(source)
    root = tree.getroot()
    view = [float(v) for v in root.get("viewBox", "0 0 512 512").split()]
    native = view[2]
    size = edge * SUPERSAMPLE
    scale = size / native

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # The background is the one rect that is a direct child of <svg>.
    for rect in root.findall(f"{SVG_NS}rect"):
        canvas.alpha_composite(_draw(size, scale, _rects(rect)))

    for group in root.findall(f"{SVG_NS}g"):
        layer = _draw(size, scale, _rects(group))
        if group.get("filter"):
            layer = layer.filter(
                ImageFilter.GaussianBlur(_blur_radius(root) * scale)
            )
        group_opacity = float(group.get("opacity", 1))
        if group_opacity < 1:
            alpha = layer.getchannel("A").point(
                lambda value, o=group_opacity: round(value * o)
            )
            layer.putalpha(alpha)
        canvas.alpha_composite(layer)

    return canvas.resize((edge, edge), Image.LANCZOS)


def main() -> int:
    if not SOURCE.exists():
        print(f"missing {SOURCE}")
        return 1
    cache: dict[int, Image.Image] = {}
    for path, edge in OUTPUTS.items():
        if edge not in cache:
            cache[edge] = render(SOURCE, edge)
        path.parent.mkdir(parents=True, exist_ok=True)
        # brands asks for lossless but properly compressed files.
        cache[edge].save(path, optimize=True)
        print(f"  {path.relative_to(ROOT)}  {edge}x{edge}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
