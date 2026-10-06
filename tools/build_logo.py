"""Generate the Clausal Prolog logo SVGs in docs/assets/logo/ (and PNGs, if
Chromium and ImageMagick are available), plus the :clausal-neck: docs icon in
docs/assets/icons/.

    python tools/build_logo.py

The mark is a snake coiled into a "C" around a squared ``:-``, coloured with a
blue-to-yellow gradient. All geometry lives here so the variants stay in sync.
"""

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "logo"

BLUE, YELLOW, NAVY, CREAM = "#3776AB", "#FFD43B", "#1E2A38", "#F6F3EA"

# Coil geometry (240x240 canvas): circle centre, radius, body width.
CX = CY = 120
R, WIDTH = 76, 28
HEAD_ANGLE = -52  # degrees, where the head joins the body
TAIL_ANGLE = 55  # degrees, where the body starts tapering
EYE = "M-6.5,0 Q0,-6.5 6.5,0 Q0,6.5 -6.5,0 Z"  # almond, scaled below
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"


def _pt(deg, r=R):
    a = math.radians(deg)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def _gradient():
    return (
        '<defs><linearGradient id="clausal-g" gradientUnits="userSpaceOnUse"'
        ' x1="0" y1="44" x2="0" y2="196">'
        f'<stop offset="0" stop-color="{BLUE}"/>'
        f'<stop offset="1" stop-color="{YELLOW}"/></linearGradient></defs>'
    )


def _snake(eye=True):
    hx, hy = _pt(HEAD_ANGLE)
    tx, ty = _pt(TAIL_ANGLE)
    # Tapered tail: outer and inner edges at the taper start, meeting at a tip.
    ox, oy = _pt(TAIL_ANGLE + 3, R + WIDTH / 2)
    ix, iy = _pt(TAIL_ANGLE + 3, R - WIDTH / 2)
    fill = 'url(#clausal-g)'
    s = (
        f'<path d="M{hx:.1f},{hy:.1f} A{R},{R} 0 1,0 {tx:.1f},{ty:.1f}"'
        f' fill="none" stroke="{fill}" stroke-width="{WIDTH}"/>'
        f'<path d="M{ox:.1f},{oy:.1f} Q184,187 181,165 Q165,166 {ix:.1f},{iy:.1f} Z" fill="{fill}"/>'
    )
    # Head: a rounded block facing right, wider than the body (after the Python logo).
    cx, cy = hx + 12, hy
    s += f'<rect x="{cx - 23:.1f}" y="{cy - 19:.1f}" width="46" height="38" rx="13" fill="{fill}"/>'
    if eye:
        s += f'<path d="{EYE}" fill="#fff" transform="translate({cx + 9:.1f} {cy - 6:.1f}) scale(1.35)"/>'
    return s


def _neck(colour):
    """The squared ':-' inside the coil."""
    return (
        f'<rect x="88" y="94" width="20" height="20" fill="{colour}"/>'
        f'<rect x="88" y="128" width="20" height="20" fill="{colour}"/>'
        f'<rect x="122" y="113" width="42" height="16" fill="{colour}"/>'
    )


def _svg(w, h, body, view=None):
    view = view or f"0 0 {w} {h}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="{w}" height="{h}"'
        ' role="img" aria-label="Clausal Prolog">'
        f"<title>Clausal Prolog</title>{_gradient()}{body}</svg>\n"
    )


def neck_icon():
    """The ':-' alone on a 24px grid, in currentColor, for docs card icons."""
    k, x0, y0 = 0.26, 2.1, 5  # scale the logo's ':-' (x 88-164, y 94-148) to fit
    rects = [(88, 94, 20, 20), (88, 128, 20, 20), (122, 113, 42, 16)]
    body = "".join(
        f'<rect x="{x0 + (x - 88) * k:.2f}" y="{y0 + (y - 94) * k:.2f}"'
        f' width="{w * k:.2f}" height="{h * k:.2f}"/>'
        for x, y, w, h in rects
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">{body}</svg>\n'


def mark(neck_colour):
    return _svg(240, 240, _snake() + _neck(neck_colour))


def icon(simple=False):
    tile = f'<rect width="240" height="240" rx="44" fill="{NAVY}"/>'
    if simple:  # for 16px: drop the ':-' and eye, which turn to mush
        return _svg(240, 240, tile + _snake(eye=False))
    return _svg(240, 240, tile + _snake() + _neck(CREAM))


def wordmark(text_colour, accent):
    g = f'<g transform="translate(0,10) scale(0.833)">{_snake()}{_neck(text_colour)}</g>'
    text = (
        f'<text x="226" y="138" font-family="{FONT}" font-size="80" font-weight="800"'
        f' fill="{text_colour}" letter-spacing="-1.5">Clausal'
        f'<tspan font-weight="400" fill="{accent}" dx="20">Prolog</tspan></text>'
    )
    return g + text


def banner():
    """Wordmark on a navy tile: reads the same on light and dark pages."""
    tile = f'<rect width="920" height="260" rx="48" fill="{NAVY}"/>'
    return _svg(920, 260, tile + f'<g transform="translate(44,20)">{wordmark(CREAM, "#8DB8E0")}</g>')


SVGS = {
    "clausal-logo.svg": mark(NAVY),
    "clausal-logo-dark.svg": mark(CREAM),
    "clausal-icon.svg": icon(),
    "clausal-icon-simple.svg": icon(simple=True),
    "clausal-wordmark.svg": _svg(820, 220, wordmark(NAVY, BLUE)),
    "clausal-wordmark-dark.svg": _svg(820, 220, wordmark(CREAM, "#8DB8E0")),
    "clausal-banner.svg": banner(),
}

PNGS = [  # (source svg, output png, width, height)
    ("clausal-logo.svg", "clausal-logo-512.png", 512, 512),
    ("clausal-logo.svg", "clausal-logo-256.png", 256, 256),
    ("clausal-logo-dark.svg", "clausal-logo-dark-512.png", 512, 512),
    ("clausal-icon.svg", "clausal-icon-512.png", 512, 512),
    ("clausal-icon.svg", "clausal-icon-192.png", 192, 192),
    ("clausal-icon.svg", "apple-touch-icon.png", 180, 180),
    ("clausal-icon.svg", "favicon-48.png", 48, 48),
    ("clausal-icon.svg", "favicon-32.png", 32, 32),
    ("clausal-icon-simple.svg", "favicon-16.png", 16, 16),
    ("clausal-wordmark.svg", "clausal-wordmark.png", 1640, 440),
    ("clausal-wordmark-dark.svg", "clausal-wordmark-dark.png", 1640, 440),
    ("clausal-banner.svg", "clausal-banner.png", 1840, 520),
]


def _chromium():
    for c in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "chromium", "google-chrome"):
        if shutil.which(c) or os.path.exists(c):
            return c
    return None


def render_pngs():
    chrome = _chromium()
    if not chrome or not shutil.which("convert"):
        print("Chromium or ImageMagick not found; skipping PNGs")
        return
    with tempfile.TemporaryDirectory() as tmp:
        for src, dst, w, h in PNGS:
            page = Path(tmp) / "page.html"
            page.write_text(
                '<html><body style="margin:0;background:transparent">'
                f'<img src="{(OUT / src).as_uri()}" width="{w}" height="{h}" style="display:block">'
                "</body></html>"
            )
            subprocess.run(
                [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                 "--allow-file-access-from-files", "--default-background-color=00000000",
                 f"--window-size={w + 400},{h + 400}", f"--screenshot={OUT / dst}", page.as_uri()],
                check=True, capture_output=True,
            )
            subprocess.run(["convert", str(OUT / dst), "-crop", f"{w}x{h}+0+0", "+repage", str(OUT / dst)],
                           check=True)
            print("wrote", dst)
    subprocess.run(
        ["convert", *(str(OUT / f) for f in ("favicon-16.png", "favicon-32.png", "favicon-48.png")),
         str(OUT / "favicon.ico")],
        check=True,
    )
    print("wrote favicon.ico")


if __name__ == "__main__":
    for name, svg in SVGS.items():
        (OUT / name).write_text(svg)
        print("wrote", name)
    # Custom icon set for mkdocs (pymdownx.emoji custom_icons): :clausal-neck:
    icons = OUT.parent / "icons" / "clausal"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "neck.svg").write_text(neck_icon())
    print("wrote icons/clausal/neck.svg")
    render_pngs()
