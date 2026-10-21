"""Draws the app icon and writes every size the three builds need into assets/.

    pip install pillow        (only needed to regenerate the icons, not to run the app)
    python3 scripts/make_icons.py

assets/icon.png            1024 px master; the desktop app's window icon; Linux .desktop icon
assets/icon.ico            Windows .exe, installer and shortcuts (16-256 px)
assets/android/res/...     Android launcher icons (legacy + adaptive), copied in by the CI build
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

# Classic theme colours (THEMES in src/cartridge_calculator.py)
BG_TOP, BG_BOTTOM = (31, 36, 46), (14, 16, 20)
BORDER = (45, 51, 63)
ACCENT, ON_ACCENT = (76, 141, 255), (255, 255, 255)
BRASS, BRASS_LIGHT, BRASS_DARK = (205, 160, 62), (240, 207, 120), (150, 112, 38)
COPPER, COPPER_LIGHT = (190, 104, 52), (226, 142, 86)
FONTS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
SS = 4          # draw 4x larger, then shrink: smooth edges


def _font(px):
    for path in FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def _ogive(cx, half_w, base_y, tip_y, steps=40):
    """Left and right edges of a bullet nose from base_y (full width) to a rounded tip."""
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps                                   # 0 at the base, 1 at the tip
        w = half_w * (1 - t ** 2.2) ** 0.62             # tangent ogive-ish curve
        y = base_y + (tip_y - base_y) * t
        left.append((cx - w, y))
        right.append((cx + w, y))
    return left, right


def draw_symbol(d, s, ox=0.0, oy=0.0):
    """Cartridge + grade badge on a 1024-unit grid scaled by s, offset by (ox, oy)."""
    X = lambda v: ox + v * s
    Y = lambda v: oy + v * s
    cx, half = 450, 118
    # case (straight-walled, like .45-70), with a lit stripe and a shaded edge
    d.rounded_rectangle([X(cx - half), Y(440), X(cx + half), Y(808)], radius=10 * s, fill=BRASS)
    d.rectangle([X(cx - half + 26), Y(446), X(cx - half + 70), Y(800)], fill=BRASS_LIGHT)
    d.rectangle([X(cx + half - 40), Y(446), X(cx + half - 4), Y(800)], fill=BRASS_DARK)
    # extractor groove and rim
    d.rectangle([X(cx - half + 18), Y(808), X(cx + half - 18), Y(838)], fill=BRASS_DARK)
    d.rounded_rectangle([X(cx - half - 12), Y(838), X(cx + half + 12), Y(884)], radius=12 * s, fill=BRASS)
    d.rectangle([X(cx - half + 4), Y(846), X(cx - half + 46), Y(876)], fill=BRASS_LIGHT)
    # bullet: a short straight bearing surface, then the nose
    bh = half - 8
    d.rectangle([X(cx - bh), Y(360), X(cx + bh), Y(446)], fill=COPPER)
    left, right = _ogive(cx, bh, 362, 120)
    d.polygon([(X(x), Y(y)) for x, y in left + right[::-1]], fill=COPPER)
    l2, _ = _ogive(cx - bh + 52, 22, 446, 196)        # highlight down the lit side of the nose
    d.polygon([(X(x), Y(y)) for x, y in l2] + [(X(cx - bh + 74), Y(446))], fill=COPPER_LIGHT)
    # crimp line where bullet meets case
    d.rectangle([X(cx - half), Y(440), X(cx + half), Y(452)], fill=BRASS_DARK)
    # grade badge: an "S" in the accent colour, ringed in the background colour
    bx, by, r = 722, 730, 168
    d.ellipse([X(bx - r - 22), Y(by - r - 22), X(bx + r + 22), Y(by + r + 22)], fill=BG_BOTTOM)
    d.ellipse([X(bx - r), Y(by - r), X(bx + r), Y(by + r)], fill=ACCENT)
    f = _font(int(250 * s))
    d.text((X(bx), Y(by + 6)), "S", font=f, fill=ON_ACCENT, anchor="mm")


def full_icon(size, round_mask=False):
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    # vertical gradient background in a rounded square (or circle)
    grad = Image.new("RGBA", (n, n))
    gd = ImageDraw.Draw(grad)
    for y in range(n):
        t = y / (n - 1)
        gd.line([(0, y), (n, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    mask = Image.new("L", (n, n), 0)
    md = ImageDraw.Draw(mask)
    if round_mask:
        md.ellipse([0, 0, n - 1, n - 1], fill=255)
    else:
        md.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.215), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if not round_mask:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.215), outline=BORDER,
                            width=max(1, n // 128))
    inset = 0.12 if round_mask else 0.0             # keep the badge inside a round icon
    s = n / 1024 * (1 - 2 * inset)
    draw_symbol(d, s, n * inset, n * inset)
    return img.resize((size, size), Image.LANCZOS)


def adaptive_foreground(size):
    """Android adaptive icon foreground: the symbol inside the 72/108 safe zone, transparent."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    safe = n * 66 / 108
    s = safe / 1024
    draw_symbol(d, s, (n - safe) / 2, (n - safe) / 2)
    return img.resize((size, size), Image.LANCZOS)


def write(img, *parts):
    path = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, optimize=True)
    return path


def main():
    master = full_icon(1024)
    write(master, "icon.png")
    master.save(os.path.join(OUT, "icon.ico"),
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    res = ("android", "res")
    for dpi, legacy, fg in (("mdpi", 48, 108), ("hdpi", 72, 162), ("xhdpi", 96, 216),
                            ("xxhdpi", 144, 324), ("xxxhdpi", 192, 432)):
        write(full_icon(legacy), *res, f"mipmap-{dpi}", "ic_launcher.png")
        write(full_icon(legacy, round_mask=True), *res, f"mipmap-{dpi}", "ic_launcher_round.png")
        write(adaptive_foreground(fg), *res, f"mipmap-{dpi}", "ic_launcher_foreground.png")
    hexbg = "#%02x%02x%02x" % BG_BOTTOM
    adaptive = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/cc_icon_background"/>\n'
                '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
                '</adaptive-icon>\n')
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        path = os.path.join(OUT, *res, "mipmap-anydpi-v26", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(adaptive)
    values = os.path.join(OUT, *res, "values")
    os.makedirs(values, exist_ok=True)
    with open(os.path.join(values, "cc_icon_background.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                 f'    <color name="cc_icon_background">{hexbg}</color>\n</resources>\n')
    print("wrote icons to", OUT)


if __name__ == "__main__":
    main()
