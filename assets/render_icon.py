#!/usr/bin/env python3
"""Prepare CompareX app icon: square 1024² RGBA from source artwork."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent
SOURCE = ASSETS / "comparex_icon_source.png"
OUTPUT = ASSETS / "comparex_icon.png"
SIZE = 1024


def _center_square_crop(im: Image.Image) -> Image.Image:
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def _is_backdrop(r: int, g: int, b: int) -> bool:
    """Light neutral pixels used as export backdrop (checkerboard / gray)."""
    if max(r, g, b) < 200:
        return False
    return max(r, g, b) - min(r, g, b) < 36


def _flood_transparent(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)

    def idx(x: int, y: int) -> int:
        return y * w + x

    stack: list[tuple[int, int]] = []
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        r, g, b = px[x, y][:3]
        if _is_backdrop(r, g, b):
            stack.append((x, y))

    while stack:
        x, y = stack.pop()
        i = idx(x, y)
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, _a = px[x, y]
        if not _is_backdrop(r, g, b):
            continue
        px[x, y] = (r, g, b, 0)
        if x > 0:
            stack.append((x - 1, y))
        if x + 1 < w:
            stack.append((x + 1, y))
        if y > 0:
            stack.append((x, y - 1))
        if y + 1 < h:
            stack.append((x, y + 1))
    return im


def render_icon(source: Path = SOURCE, output: Path = OUTPUT) -> None:
    if not source.is_file():
        raise FileNotFoundError(
            f"Missing {source.name}. Save the approved artwork as this file."
        )
    im = Image.open(source)
    im = _center_square_crop(im)
    im = im.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    im = _flood_transparent(im)
    im.save(output, "PNG")
    alpha = im.split()[-1].getextrema()
    print(f"Wrote {output} ({im.size[0]}x{im.size[1]}, alpha {alpha})")


if __name__ == "__main__":
    render_icon()
