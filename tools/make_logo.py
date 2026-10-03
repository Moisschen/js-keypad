"""JS-Keypad logo: rounded app tile with a blue-violet gradient, the staggered 4x3 key field (middle finger column
highest, like the real keypad) and the thumb stick. One geometry, written as SVG (web) and rendered with Pillow
(favicons, PWA icons, Windows .ico, tray icons).

    python tools/make_logo.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
APP = ROOT / "app"

# 100 x 100 design grid
TILE_R = 22
GRAD = ("#2563eb", "#7c3aed")               # top-left -> bottom-right
KEY = 13.0                                   # key size
KEY_R = 3.2
COL_X = [14.0, 30.5, 47.0, 63.5]             # pinky, ring, middle, index (left hand)
COL_Y = [33.0, 24.0, 20.0, 26.0]             # top of each column: middle finger reaches furthest
ROW_PITCH = 15.5
STICK = (77.0, 76.0, 12.5)                   # cx, cy, r
STICK_DOT = 5.2


def keys():
    for c, (x, y0) in enumerate(zip(COL_X, COL_Y)):
        for r in range(3):
            y = y0 + r * ROW_PITCH
            if c == 3 and r == 2:
                continue                     # space for the stick, keeps the mark readable
            yield x, y, (c == 2 and r == 1)  # one accent key (home row, middle finger)


def svg(size=100):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">',
             '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
             f'<stop offset="0" stop-color="{GRAD[0]}"/><stop offset="1" stop-color="{GRAD[1]}"/></linearGradient>'
             '<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/>'
             '<stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>',
             f'<rect width="100" height="100" rx="{TILE_R}" fill="url(#g)"/>',
             f'<rect width="100" height="100" rx="{TILE_R}" fill="url(#s)"/>']
    for x, y, accent in keys():
        fill = "#5eead4" if accent else "#ffffff"
        parts.append(f'<rect x="{x}" y="{y}" width="{KEY}" height="{KEY}" rx="{KEY_R}" fill="{fill}" fill-opacity=".95"/>')
    cx, cy, r = STICK
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#fff" stroke-width="3.2" stroke-opacity=".95"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{STICK_DOT}" fill="#fff"/>')
    parts.append("</svg>")
    return "".join(parts)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render(size, active_dot=None):
    """Pillow rendering of the same geometry (4x supersampled). active_dot: RGB of a status dot (tray)."""
    s = size * 4
    k = s / 100
    a, b = hex_rgb(GRAD[0]), hex_rgb(GRAD[1])
    grad = Image.new("RGB", (s, s))
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), TILE_R * k, fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    # soft top light
    shine = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    for y in range(int(s * .55)):
        sd.line([(0, y), (s, y)], fill=(255, 255, 255, int(56 * (1 - y / (s * .55)))))
    img = Image.alpha_composite(img, Image.composite(shine, Image.new("RGBA", (s, s)), mask))
    d = ImageDraw.Draw(img)
    for x, y, accent in keys():
        col = (94, 234, 212, 245) if accent else (255, 255, 255, 242)
        d.rounded_rectangle((x * k, y * k, (x + KEY) * k, (y + KEY) * k), KEY_R * k, fill=col)
    cx, cy, r = STICK
    w = 3.2 * k
    d.ellipse(((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k), outline=(255, 255, 255, 242), width=round(w))
    d.ellipse(((cx - STICK_DOT) * k, (cy - STICK_DOT) * k, (cx + STICK_DOT) * k, (cy + STICK_DOT) * k), fill=(255, 255, 255))
    if active_dot:
        rr = 17 * k
        d.ellipse((s - 2 * rr - 2 * k, s - 2 * rr - 2 * k, s - 2 * k, s - 2 * k), fill=active_dot + (255,),
                  outline=(18, 21, 27, 255), width=round(4 * k))
    return img.resize((size, size), Image.LANCZOS)


def main():
    (DOCS / "logo.svg").write_text(svg(), encoding="utf-8")
    for size in (32, 180, 192, 512):
        render(size).save(DOCS / f"icon-{size}.png")
    big = render(256)
    big.save(APP / "icon.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (256, 256)])
    render(64).save(APP / "tray.png")
    render(64, active_dot=(34, 197, 94)).save(APP / "tray-active.png")
    print("Logo geschrieben: docs/logo.svg, docs/icon-*.png, app/icon.ico, app/tray*.png")


if __name__ == "__main__":
    main()
