"""Draws the app icon and writes every size the three builds need into assets/.

    pip install pillow        (only needed to regenerate the icons, not to run the app)
    python3 scripts/make_icons.py

assets/icon.png            1024 px master; the desktop app's window icon; Linux .desktop icon
assets/icon.ico            Windows .exe, installer and shortcuts (16-256 px)
assets/android/res/...     Android launcher icons (legacy + adaptive), copied in by the CI build
assets/web/...             web version: home-screen icons (iPhone apple-touch-icon, manifest icons)
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

# Classic theme colors (THEMES in src/load_lore.py)
BG_TOP, BG_BOTTOM = (31, 36, 46), (14, 16, 20)
BORDER = (45, 51, 63)
ACCENT, ON_ACCENT = (76, 141, 255), (255, 255, 255)
ACCENT_DARK, ACCENT_LIGHT = (44, 92, 186), (130, 176, 255)
PAGES, PAGES_SHADE = (238, 230, 210), (200, 190, 166)
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


def draw_cartridge(d, X, Y, cx=450, half=112):
    """A bottlenecked rifle cartridge on the 1024-unit grid (X / Y map grid units to pixels)."""
    neck, shoulder_top, shoulder_bot, mouth = 60, 330, 410, 250
    body = [(cx - half, 808), (cx - half, shoulder_bot), (cx - neck, shoulder_top), (cx - neck, mouth),
            (cx + neck, mouth), (cx + neck, shoulder_top), (cx + half, shoulder_bot), (cx + half, 808)]
    # bullet first (the case mouth overlaps its base): a spitzer nose to a sharp-ish tip
    left, right = _ogive(cx, neck - 4, 262, 40)
    d.polygon([(X(x), Y(y)) for x, y in left + right[::-1]], fill=COPPER)
    l2, _ = _ogive(cx - neck + 30, 12, 262, 110)      # highlight down the lit side of the nose
    d.polygon([(X(x), Y(y)) for x, y in l2] + [(X(cx - neck + 44), Y(262))], fill=COPPER_LIGHT)
    d.polygon([(X(x), Y(y)) for x, y in body], fill=BRASS)
    # lit stripe and shaded edge follow the body, shoulder and neck
    d.polygon([(X(x), Y(y)) for x, y in [(cx - half + 24, 800), (cx - half + 24, shoulder_bot + 8),
                                         (cx - half + 66, shoulder_bot - 18), (cx - half + 66, 800)]],
              fill=BRASS_LIGHT)
    d.rectangle([X(cx - neck + 14), Y(mouth + 8), X(cx - neck + 30), Y(shoulder_top + 4)], fill=BRASS_LIGHT)
    d.polygon([(X(x), Y(y)) for x, y in [(cx + half - 38, 800), (cx + half - 38, shoulder_bot - 4),
                                         (cx + half, shoulder_bot), (cx + half, 800)]], fill=BRASS_DARK)
    # extractor groove and rim
    d.rectangle([X(cx - half + 18), Y(808), X(cx + half - 18), Y(838)], fill=BRASS_DARK)
    d.rounded_rectangle([X(cx - half - 4), Y(838), X(cx + half + 4), Y(884)], radius=X(12) - X(0),
                        fill=BRASS)
    d.rectangle([X(cx - half + 8), Y(846), X(cx - half + 50), Y(876)], fill=BRASS_LIGHT)


def draw_book(d, X, Y):
    """A closed hardcover book lying flat (spine on the left, page edges facing out)."""
    l, r, top, bot = 196, 820, 742, 892
    # back cover peeks out under the pages, front cover on top
    d.rounded_rectangle([X(l), Y(bot - 30), X(r + 14), Y(bot)], radius=X(14) - X(0), fill=ACCENT_DARK)
    d.rectangle([X(l + 40), Y(top + 30), X(r), Y(bot - 22)], fill=PAGES)
    for k in range(1, 5):                              # page lines on the fore edge
        yy = top + 30 + k * (bot - 52 - top - 30) / 5
        d.rectangle([X(l + 48), Y(yy - 3), X(r - 6), Y(yy + 3)], fill=PAGES_SHADE)
    d.rounded_rectangle([X(l), Y(top), X(r + 14), Y(top + 38)], radius=X(14) - X(0), fill=ACCENT)
    # spine, rounded, with two bands
    d.rounded_rectangle([X(l - 8), Y(top), X(l + 58), Y(bot)], radius=X(26) - X(0), fill=ACCENT)
    for yy in (top + 48, bot - 62):
        d.rectangle([X(l - 8), Y(yy), X(l + 58), Y(yy + 12)], fill=ACCENT_DARK)
    d.rectangle([X(l + 8), Y(top + 8), X(l + 20), Y(bot - 8)], fill=ACCENT_LIGHT)   # lit edge


def draw_symbol(d, s, ox=0.0, oy=0.0):
    """A cartridge standing on a book (load lore) on a 1024-unit grid scaled by s, offset (ox, oy)."""
    X = lambda v: ox + v * s
    Y = lambda v: oy + v * s
    draw_book(d, X, Y)
    # the cartridge stands on the book: 0.76 scale, rim resting on the cover, centred
    k, cx = 0.76, 512
    Xc = lambda v: X(cx + (v - 450) * k)
    Yc = lambda v: Y(742 - (884 - v) * k)
    draw_cartridge(d, Xc, Yc)


def full_icon(size, round_mask=False, square=False):
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
    if square:                                      # iOS rounds the corners itself
        md.rectangle([0, 0, n - 1, n - 1], fill=255)
    elif round_mask:
        md.ellipse([0, 0, n - 1, n - 1], fill=255)
    else:
        md.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.215), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if not round_mask and not square:
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
    write(full_icon(180, square=True), "web", "apple-touch-icon.png")
    for px in (192, 512):
        write(full_icon(px), "web", f"icon-{px}.png")
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
