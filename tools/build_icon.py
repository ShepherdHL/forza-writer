"""Build the app icon: FW as two braille cells (F = dots 1,2,4, W = dots
2,4,5,6) in Forza Writer orange and off-white, with faint
"ghost" dots at unfilled positions so it reads as an authentic braille
cell rather than a random dot cluster.

Writes a real multi-resolution `assets/icon.ico` (transparent background,
PNG-encoded frames, natively supported since Windows Vista, no legacy
BMP encoding needed) plus a full-resolution `assets/icon.png` for
reference/README use. Small and desktop-size frames use the deliberately
simple orange/white two-dot mark; larger brand surfaces use the full FW.

Usage:
    python tools/build_icon.py
"""
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Stable brand colors, intentionally independent of the selectable GUI
# palette. These match the supplied reference artwork.
ACCENT = (204, 106, 46)
FG = (232, 235, 240)

F_DOTS = {1, 2, 4}
W_DOTS = {2, 4, 5, 6}
# dot position -> (col, row) in a 2-wide x 3-tall braille cell
POS = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SIMPLIFIED_MAX_SIZE = 48
REFERENCE_SIZE = 512  # full-pattern source resolution before downscaling

WORDMARK_SOURCE = ASSETS_DIR / "wordmark-ja-source.png"
WORDMARK_PATH = ASSETS_DIR / "wordmark-ja.png"
WORDMARK_BG = (4, 5, 5)
WORDMARK_ORANGE = ACCENT
WORDMARK_BRONZE = (148, 112, 74)


def _colors():
    return ACCENT, FG


def render_braille_cells(size: int, f_color, w_color, ghost_alpha: int = 60) -> Image.Image:
    """Render the full FW mark on a square transparent canvas.

    Drawing at 4x and downsampling keeps the circles smooth while their
    normalized centers remain optically stable at every ICO resolution.
    """
    scale = 4
    work_size = size * scale
    dot_r = work_size * 0.070
    x_positions = [work_size * x for x in (0.17, 0.38, 0.62, 0.83)]
    y_positions = [work_size * y for y in (0.20, 0.50, 0.80)]
    img = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ghost = (*w_color, ghost_alpha)

    def draw_cell(column_offset, dots, color):
        for d, (c, r) in POS.items():
            cx = x_positions[column_offset + c]
            cy = y_positions[r]
            fill = (*color, 255) if d in dots else ghost
            draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=fill)

    draw_cell(0, F_DOTS, f_color)
    draw_cell(2, W_DOTS, w_color)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def render_simplified(size: int, f_color, w_color) -> Image.Image:
    """Functional small-size mark: one orange dot and one white dot."""
    scale = 4
    work_size = size * scale
    img = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = work_size * 0.19
    cy = work_size / 2
    for cx, color in ((work_size * 0.28, f_color), (work_size * 0.72, w_color)):
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*color, 255))
    return img.resize((size, size), Image.Resampling.LANCZOS)


def clean_wordmark(source: Image.Image) -> Image.Image:
    """Remove the supplied near-black matte without leaving dark edge halos.

    Each antialiased pixel is reconstructed as exact brand color plus alpha,
    selecting orange for the Japanese title and bronze for the English line.
    """
    src = source.convert("RGB")
    out = Image.new("RGBA", src.size, (0, 0, 0, 0))
    split_y = round(src.height * 0.66)
    for y in range(src.height):
        target = WORDMARK_ORANGE if y < split_y else WORDMARK_BRONZE
        for x in range(src.width):
            pixel = src.getpixel((x, y))
            estimates = [
                (pixel[i] - WORDMARK_BG[i]) / (target[i] - WORDMARK_BG[i])
                for i in range(3) if target[i] != WORDMARK_BG[i]
            ]
            alpha = max(0.0, min(1.0, sum(estimates) / len(estimates)))
            if alpha > 0.015:
                out.putpixel((x, y), (*target, round(alpha * 255)))
    return out


def _square(img: Image.Image, size: int) -> Image.Image:
    """Fit `img` into a transparent size x size canvas, preserving aspect."""
    fit = min(size / img.width, size / img.height)
    resized = img.resize((max(1, round(img.width * fit)), max(1, round(img.height * fit))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    return canvas


def write_ico(images: dict[int, Image.Image], out_path: Path) -> None:
    """Manual "PNG-in-ICO" writer: each directory entry's image data is a
    real PNG, natively supported since Windows Vista, so different sizes
    can carry genuinely different artwork instead of one image resized
    uniformly (Pillow's own ICO writer only supports the latter)."""
    sizes = sorted(images)
    entries = []
    payloads = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        buf = BytesIO()
        images[size].save(buf, format="PNG")
        data = buf.getvalue()
        dim_byte = size if size < 256 else 0
        entries.append(struct.pack("<BBBBHHII", dim_byte, dim_byte, 0, 0, 1, 32, len(data), offset))
        payloads.append(data)
        offset += len(data)

    with open(out_path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        for entry in entries:
            f.write(entry)
        for payload in payloads:
            f.write(payload)


def build():
    accent, fg = _colors()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    full = render_braille_cells(REFERENCE_SIZE, accent, fg)
    full.save(ASSETS_DIR / "icon.png")

    images = {}
    for size in ICO_SIZES:
        images[size] = (render_simplified(size, accent, fg)
                        if size <= SIMPLIFIED_MAX_SIZE
                        else render_braille_cells(size, accent, fg))
    write_ico(images, ASSETS_DIR / "icon.ico")
    if WORDMARK_SOURCE.exists():
        clean_wordmark(Image.open(WORDMARK_SOURCE)).save(WORDMARK_PATH)
    print(f"Wrote {ASSETS_DIR / 'icon.ico'} ({len(images)} sizes: {sorted(images)})")
    print(f"Wrote {ASSETS_DIR / 'icon.png'} ({full.size[0]}x{full.size[1]})")
    if WORDMARK_PATH.exists():
        print(f"Wrote {WORDMARK_PATH}")


if __name__ == "__main__":
    build()
