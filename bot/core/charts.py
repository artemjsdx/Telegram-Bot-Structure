"""
Code-generated charts for stats screens — dark, mostly black-&-white with a
single restrained accent, 16:9 (1280×720) to match the menu banner.

Rendered at 2× and downscaled with LANCZOS for clean anti-aliasing, so the
result looks smooth without any heavy plotting dependency (just Pillow).

Public API:
    render_daily_chart(rows, title, subtitle="", legend=None) -> bytes (PNG)
        rows = [(label, v1)] or [(label, v1, v2)]  (one or two series)
        legend = ("Series A", "Series B")  shown top-right for two-series charts
"""
from __future__ import annotations

import io
import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:  # noqa: BLE001 — Pillow not installed yet (e.g. fresh deploy)
    Image = ImageDraw = ImageFont = None  # type: ignore
    _PIL_OK = False

# ── geometry (final pixels; everything is multiplied by S while drawing) ──
W, H = 1280, 720
S = 2                       # supersampling factor
M_LEFT, M_RIGHT = 76, 44
M_TOP, M_BOTTOM = 116, 74

# ── palette ──
BG_TOP = (18, 19, 24)       # subtle vertical gradient on the canvas
BG_BOT = (12, 13, 17)
GRID = (38, 40, 47)
AXIS = (70, 75, 84)
TITLE_C = (242, 244, 248)
SUB_C = (138, 144, 155)
LABEL_C = (122, 128, 138)
MAIN_TOP = (226, 230, 237)  # primary series (processed / joined): light gray
MAIN_BOT = (150, 156, 166)
ACCENT_TOP = (224, 96, 84)  # secondary series (failed / left): muted red
ACCENT_BOT = (158, 58, 50)

_FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts"
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, name), size * S)
    except OSError:
        return ImageFont.load_default()


def _nice_max(v: float) -> int:
    if v <= 5:
        return 5
    exp = math.floor(math.log10(v))
    base = 10 ** exp
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * base >= v:
            return int(round(m * base))
    return int(10 * base)


def _vgrad(w: int, h: int, top: tuple, bot: tuple) -> Image.Image:
    """A 1-pixel-wide vertical gradient stretched to (w, h)."""
    col = Image.new("RGB", (1, max(1, h)))
    px = col.load()
    n = max(1, h - 1)
    for y in range(h):
        t = y / n
        px[0, y] = tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return col.resize((max(1, w), max(1, h)))


def _bar(img: Image.Image, x: int, y: int, w: int, h: int, top: tuple, bot: tuple) -> None:
    """Paste a gradient-filled, round-topped bar onto img."""
    if h <= 0 or w <= 0:
        return
    radius = min(w // 2, 10 * S)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    # square off the very bottom so the bar sits flush on the baseline
    md.rectangle([0, h - radius, w - 1, h - 1], fill=255)
    img.paste(_vgrad(w, h, top, bot), (x, y), mask)


def _ctext(d: ImageDraw.ImageDraw, cx: int, y: int, text: str, font, fill) -> None:
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2] - bb[0]) / 2, y), text, font=font, fill=fill)


def render_daily_chart(
    rows: list[tuple],
    title: str,
    subtitle: str = "",
    legend: tuple[str, str] | None = None,
) -> bytes:
    """Render a dark grouped/​single bar chart and return PNG bytes."""
    if not _PIL_OK:
        # Pillow missing — signal the caller to fall back to a text-only screen.
        raise RuntimeError("Pillow is not installed; chart rendering unavailable")
    sw, sh = W * S, H * S
    img = _vgrad(sw, sh, BG_TOP, BG_BOT)
    d = ImageDraw.Draw(img)

    f_title = _font(34, bold=True)
    f_sub = _font(18)
    f_axis = _font(16)
    f_val = _font(15, bold=True)

    # plot rectangle (in 2× coords)
    px0, py0 = M_LEFT * S, M_TOP * S
    px1, py1 = (W - M_RIGHT) * S, (H - M_BOTTOM) * S
    plot_w, plot_h = px1 - px0, py1 - py0

    n_series = max(1, len(rows[0]) - 1) if rows else 1
    raw_max = 0
    for r in rows:
        for v in r[1:]:
            raw_max = max(raw_max, v)
    ymax = _nice_max(raw_max)

    # ── header ──
    d.text((M_LEFT * S, 34 * S), title, font=f_title, fill=TITLE_C)
    if subtitle:
        d.text((M_LEFT * S, 78 * S), subtitle, font=f_sub, fill=SUB_C)

    # ── legend (top-right) ──
    if legend and n_series == 2:
        cols = [(MAIN_TOP, legend[0]), (ACCENT_TOP, legend[1])]
        lx = px1
        for color, name in reversed(cols):
            bb = d.textbbox((0, 0), name, font=f_axis)
            tw = bb[2] - bb[0]
            lx -= tw
            d.text((lx, 40 * S), name, font=f_axis, fill=SUB_C)
            lx -= 14 * S
            d.rounded_rectangle(
                [lx, 42 * S, lx + 9 * S, 51 * S], radius=3 * S, fill=color
            )
            lx -= 24 * S

    # ── y grid + labels ──
    divs = 4
    for i in range(divs + 1):
        gy = py1 - plot_h * i / divs
        d.line([(px0, gy), (px1, gy)], fill=GRID, width=max(1, S))
        val = round(ymax * i / divs)
        bb = d.textbbox((0, 0), str(val), font=f_axis)
        d.text(
            (px0 - 12 * S - (bb[2] - bb[0]), gy - (bb[3] - bb[1]) / 2 - bb[1]),
            str(val), font=f_axis, fill=LABEL_C,
        )
    d.line([(px0, py1), (px1, py1)], fill=AXIS, width=max(1, S))

    # ── bars ──
    n = len(rows) or 1
    slot = plot_w / n
    show_vals = n <= 10
    lbl_step = max(1, math.ceil(n / 12))
    palettes = [(MAIN_TOP, MAIN_BOT), (ACCENT_TOP, ACCENT_BOT)]

    for i, row in enumerate(rows):
        label = row[0]
        values = list(row[1:])
        slot_x = px0 + slot * i
        group_w = slot * 0.62
        gap = slot * 0.06
        bar_w = (group_w - gap * (n_series - 1)) / n_series
        gx = slot_x + (slot - group_w) / 2
        for si, v in enumerate(values):
            bh = int(plot_h * (v / ymax)) if ymax else 0
            bx = int(gx + si * (bar_w + gap))
            by = int(py1 - bh)
            top, bot = palettes[si]
            _bar(img, bx, by, int(bar_w), bh, top, bot)
            if show_vals and v > 0:
                _ctext(d, bx + bar_w / 2, by - 22 * S, str(v), f_val, top)
        if i % lbl_step == 0:
            _ctext(d, slot_x + slot / 2, py1 + 14 * S, label, f_axis, LABEL_C)

    out = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
