#!/usr/bin/env python3
"""
Cartridge Value Calculator - a desktop tool for comparing ammunition by
performance per dollar.

On startup you choose a category (Centerfire Rifle, Handgun, Rimfire Rifle or
Shotgun). Pick a cartridge and load, enter what you pay per round and the
distance you care about, and the program grades velocity, energy, recoil and
cost (S-F) plus an overall score.

Each category has its own data file (in data/ in the repo, or next to the program
when packaged):
    ammo_centerfire_rifle.csv   ammo_handgun.csv
    ammo_rimfire_rifle.csv      ammo_shotgun.csv
Add or edit rows there, or use "Add your own caliber" inside the program (those
entries are saved to my_calibers.csv).

Scoring: every factor is scored on a curve, relative to a typical load in the
same category, so extra speed or energy past a point earns less and less.

Ballistics: velocity at distance is computed by integrating the standard G1
drag model using each load's G1 ballistic coefficient. Recoil is an estimate
of free recoil energy for a gun of the weight you enter.

Requires only Python 3.8+ with Tkinter (included with the standard installers
for Windows and macOS).
"""

import bisect
import csv
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except ImportError:  # lets the calculation code be imported/tested without a GUI
    tk = None

# --------------------------------------------------------------------------- #
# Settings you may want to tweak
# --------------------------------------------------------------------------- #
APP_TITLE = "Cartridge Value Calculator"
GRAINS_PER_OZ = 437.5
CUSTOM_FILENAME = "my_calibers.csv"
SETTINGS_FILENAME = "settings.json"
HANDLOAD_FILENAME = "my_handloads.csv"
BULLETS_FILENAME = "bullets.csv"
HANDLOAD_FIELDS = ["id", "category", "cartridge", "name", "bullet_maker", "bullet", "bullet_gr",
                   "diameter_in", "bc_g1", "powder", "powder_gr", "muzzle_fps", "barrel_in",
                   "purpose", "cost", "bullet_cost", "powder_cost_lb", "primer_cost",
                   "brass_cost", "brass_reuse", "notes"]
PURPOSES = ["Hunting", "Varmint", "Target", "Match", "Defense", "Subsonic"]
POWDERS = [
    "H4350", "H4831SC", "H1000", "Varget", "H4895", "H335", "H322", "CFE 223", "Benchmark",
    "Lil'Gun", "H110", "H4198", "Titegroup", "Longshot", "Universal", "Clays", "HS-6", "H380",
    "Retumbo", "Superformance", "H414", "H4227",
    "IMR 4064", "IMR 4350", "IMR 4895", "IMR 4831", "IMR 3031", "IMR 7828", "IMR 4198",
    "IMR 8208 XBR", "IMR 4227", "IMR 4759",
    "Reloder 7", "Reloder 10X", "Reloder 15", "Reloder 16", "Reloder 17", "Reloder 19",
    "Reloder 22", "Reloder 23", "Reloder 25", "Reloder 26", "Reloder 33", "Reloder 50",
    "Unique", "Bullseye", "Power Pistol", "Blue Dot", "Red Dot", "2400", "Green Dot", "Herco",
    "Sport Pistol", "Winchester 231", "Winchester 296", "Winchester 748", "Winchester 760",
    "AutoComp", "WSF", "StaBall 6.5",
    "Accurate 2230", "Accurate 2460", "Accurate 2520", "Accurate 4350", "Accurate 5744",
    "Accurate No.2", "Accurate No.5", "Accurate No.7", "Accurate No.9",
    "Vihtavuori N140", "Vihtavuori N150", "Vihtavuori N160", "Vihtavuori N165",
    "Vihtavuori N133", "Vihtavuori N550", "Vihtavuori N320", "Vihtavuori N340",
    "Vihtavuori N350", "Ramshot Big Boy", "Ramshot TAC", "Ramshot X-Terminator",
    "Ramshot Enforcer", "Ramshot Silhouette", "Ramshot Competition", "Norma 202", "Norma 203B",
]
CUSTOM_FIELDS = ["category", "cartridge", "load", "bullet_gr", "muzzle_fps",
                 "bc_g1", "powder_gr", "default_cost", "diameter_in"]

# Score (0-100) needed for each letter grade; anything lower is an F.
# Scores cluster tightly by design (a typical load is ~70), so the bands are
# narrow; they were tuned so each category spreads across S-F.
GRADE_BANDS = [(72.5, "S"), (70.5, "A"), (66, "B"), (61, "C"), (55, "D")]

# metric key -> (display name, higher is better?)
METRICS = {
    "velocity": ("Velocity", True),
    "energy": ("Energy", True),
    "recoil": ("Recoil", False),
    "cost": ("Cost", False),
    "taylor": ("Taylor KO", True),      # Taylor Knock-Out factor (bullet weight x velocity x diameter)
}
TERMINAL_KEYS = ("taylor",)            # needs a bullet diameter, so it doesn't apply to shotshells
# Default scoring weights: velocity / energy / recoil / cost / Taylor KO.
# 3 / 3 / 1 / 3 -> 30% / 30% / 10% / 30%.  Taylor KO is shown everywhere but only
# changes the grades once you give it a weight (open "Scoring weights").
DEFAULT_WEIGHTS = (3, 3, 1, 3, 0)

# Curve shape. A load that matches the category's typical (median) value for a
# factor scores TYPICAL_SCORE on it. Higher-is-better factors climb toward 100
# with diminishing returns; lower-is-better factors fall away more gently.
TYPICAL_SCORE = 70.0
_HIGH_K = -math.log(1.0 - TYPICAL_SCORE / 100.0)
_LOW_K = -math.log(TYPICAL_SCORE / 100.0)


@dataclass(frozen=True)
class Category:
    title: str
    blurb: str
    filename: str
    default_distance: float      # yards
    max_distance: float          # yards
    default_gun_lb: float
    gun_label: str
    cartridge_label: str = "CARTRIDGE"
    load_label: str = "BULLET WEIGHT"
    payload_row: str = "Bullet weight"
    payload_col: str = "Grains"
    grain_style: bool = True     # dropdown reads "168 gr  ·  ELD-M"; False = group + load text
    show_oz: bool = False        # also show payload in ounces (shotgun)
    legacy_filename: str = ""    # older file name to fall back to
    weights: tuple = DEFAULT_WEIGHTS   # velocity, energy, recoil, cost
    allow_custom: bool = True    # show "Add your own caliber"
    default_bc: float = 0.30     # used when a custom entry leaves BC blank
    sort_loads: bool = True      # sort the load dropdown by weight (False = keep file order)
    loads_filename: str = ""     # detailed manufacturer loads for the 'Compare Loads' tab
    terminal: bool = True        # show Taylor KO (needs a bullet diameter; not for shot)


CATEGORIES = (
    Category("Centerfire Rifle", "Hunting, precision and military rounds",
             "ammo_centerfire_rifle.csv", 100, 2000, 8.0, "RIFLE WEIGHT (LB)",
             legacy_filename="ammo_data.csv", default_bc=0.30,
             loads_filename="loads_centerfire_rifle.csv"),
    Category("Handgun", "Pistol and revolver rounds",
             "ammo_handgun.csv", 10, 500, 2.0, "HANDGUN WEIGHT (LB)", default_bc=0.15,
             loads_filename="loads_handgun.csv"),
    Category("Rimfire Rifle", "Small-bore rimfire rounds",
             "ammo_rimfire_rifle.csv", 50, 500, 5.0, "RIFLE WEIGHT (LB)",
             weights=(3, 3, 1, 6, 0), default_bc=0.13,
             loads_filename="loads_rimfire_rifle.csv"),
    Category("Shotgun", "Birdshot, buckshot and slugs",
             "ammo_shotgun.csv", 25, 300, 7.5, "SHOTGUN WEIGHT (LB)",
             cartridge_label="GAUGE", load_label="LOAD", payload_row="Payload",
             payload_col="Payload (gr)", grain_style=False, show_oz=True,
             allow_custom=False, sort_loads=False, terminal=False,
             loads_filename="loads_shotgun.csv"),
)


def default_weights(cat):
    return dict(zip(METRICS, cat.weights))


def metric_keys(cat):
    """The factors that apply to a category (shotshells have no bullet diameter)."""
    return [k for k in METRICS if cat.terminal or k not in TERMINAL_KEYS]


# Dark theme palette
BG = "#0e1014"
SURFACE = "#171a21"
SURFACE_2 = "#222732"
BORDER = "#2d333f"
TEXT = "#e8eaee"
MUTED = "#8a93a3"
ACCENT = "#4c8dff"
ACCENT_HOVER = "#6aa0ff"

# grade -> (background, foreground)
GRADE_COLORS = {
    "S": ("#a98bff", "#1b0a40"),
    "A": ("#2fbf71", "#06210f"),
    "B": ("#4c8dff", "#06152e"),
    "C": ("#e5b93c", "#2b2005"),
    "D": ("#e98a3c", "#2e1704"),
    "F": ("#e5534b", "#2e0a08"),
}

SOURCE_NOTES = {
    "catalog": "Weight and velocity come from the manufacturer's 2026 catalog. The ballistic "
               "coefficient is the catalog's own figure or is worked out from its published "
               "downrange velocities; powder charge (recoil) and price are estimated.",
    "published": "Weight, velocity and ballistic coefficient are manufacturer-published; "
                 "powder charge (used for recoil) is estimated.",
    "partial": "Weight and velocity are manufacturer-published; ballistic coefficient and "
               "powder charge are estimated.",
    "custom": "Your own entry. Anything you left blank was estimated.",
    "typical": "Typical factory-load figures from published specs; approximate, so check the box.",
    "handload": "Your own handload. Check every figure against a published load manual.",
}
DEFAULT_SOURCE_NOTE = ("Load data is approximate. Check it against the box or the "
                       "manufacturer, and edit the data file if needed.")

# --------------------------------------------------------------------------- #
# Ballistics
# --------------------------------------------------------------------------- #
# Standard G1 drag function: (Mach, Cd)
G1_TABLE = [
    (0.00, 0.2629), (0.05, 0.2558), (0.10, 0.2487), (0.15, 0.2413),
    (0.20, 0.2344), (0.25, 0.2278), (0.30, 0.2214), (0.35, 0.2155),
    (0.40, 0.2104), (0.45, 0.2061), (0.50, 0.2032), (0.55, 0.2020),
    (0.60, 0.2034), (0.70, 0.2165), (0.725, 0.2230), (0.75, 0.2313),
    (0.775, 0.2417), (0.80, 0.2546), (0.825, 0.2706), (0.85, 0.2901),
    (0.875, 0.3136), (0.90, 0.3415), (0.925, 0.3734), (0.95, 0.4084),
    (0.975, 0.4448), (1.0, 0.4805), (1.025, 0.5136), (1.05, 0.5427),
    (1.075, 0.5677), (1.10, 0.5883), (1.125, 0.6053), (1.15, 0.6191),
    (1.20, 0.6393), (1.25, 0.6518), (1.30, 0.6589), (1.35, 0.6621),
    (1.40, 0.6625), (1.45, 0.6607), (1.50, 0.6573), (1.55, 0.6528),
    (1.60, 0.6474), (1.65, 0.6413), (1.70, 0.6347), (1.75, 0.6280),
    (1.80, 0.6210), (1.85, 0.6141), (1.90, 0.6072), (1.95, 0.6003),
    (2.00, 0.5934), (2.05, 0.5867), (2.10, 0.5804), (2.15, 0.5743),
    (2.20, 0.5685), (2.25, 0.5630), (2.30, 0.5577), (2.35, 0.5527),
    (2.40, 0.5481), (2.45, 0.5438), (2.50, 0.5397), (2.60, 0.5325),
    (2.70, 0.5264), (2.80, 0.5211), (2.90, 0.5168), (3.00, 0.5133),
    (3.10, 0.5105), (3.20, 0.5084), (3.30, 0.5067), (3.40, 0.5054),
    (3.50, 0.5040), (3.60, 0.5030), (3.70, 0.5022), (3.80, 0.5016),
    (3.90, 0.5010), (4.00, 0.5006), (4.20, 0.4998), (4.40, 0.4995),
    (4.60, 0.4992), (4.80, 0.4990), (5.00, 0.4988),
]
_G1_MACH = [m for m, _ in G1_TABLE]
_G1_CD = [c for _, c in G1_TABLE]

FT_PER_M = 3.280839895
YD_PER_M = 1.093613298
SPEED_OF_SOUND_MS = 340.3          # standard sea-level atmosphere
AIR_DENSITY = 1.225                # kg/m^3, standard sea-level atmosphere
LB_IN2_TO_KG_M2 = 703.0696
# Drag constant: dv/dx = -K * Cd(M) * v / BC   (BC in lb/in^2, v in m/s, x in m)
_K = AIR_DENSITY * math.pi / (8.0 * LB_IN2_TO_KG_M2)


def g1_cd(mach):
    """Linear interpolation of the G1 drag coefficient."""
    if mach <= _G1_MACH[0]:
        return _G1_CD[0]
    if mach >= _G1_MACH[-1]:
        return _G1_CD[-1]
    i = bisect.bisect_right(_G1_MACH, mach)
    m0, m1 = _G1_MACH[i - 1], _G1_MACH[i]
    c0, c1 = _G1_CD[i - 1], _G1_CD[i]
    return c0 + (c1 - c0) * (mach - m0) / (m1 - m0)


def velocity_at(muzzle_fps, bc_g1, distance_yd):
    """Velocity (fps) after travelling distance_yd, using G1 drag + BC."""
    if distance_yd <= 0:
        return float(muzzle_fps)
    v = muzzle_fps / FT_PER_M                     # m/s
    total_m = distance_yd / YD_PER_M
    step = 0.5                                    # metres
    x = 0.0

    def dvdx(speed):
        return -_K * g1_cd(speed / SPEED_OF_SOUND_MS) * speed / bc_g1

    while x < total_m and v > 1.0:
        h = min(step, total_m - x)
        k1 = dvdx(v)
        k2 = dvdx(v + 0.5 * h * k1)
        v += h * k2                               # midpoint (RK2) step
        x += h
    return max(v, 0.0) * FT_PER_M


def energy_ftlbs(bullet_gr, velocity_fps):
    return bullet_gr * velocity_fps ** 2 / 450240.0


def recoil_ftlbs(bullet_gr, muzzle_fps, powder_gr, gun_lb):
    """Estimated free recoil energy (ft-lbs).

    Uses the common approximation that propellant gas leaves at ~4000 fps and
    contributes 1.75x its weight to the ejected momentum.
    """
    ejecta_momentum = (bullet_gr * muzzle_fps + 1.75 * powder_gr * 4000.0) / 7000.0
    gun_velocity = ejecta_momentum / gun_lb        # ft/s
    return 0.5 * (gun_lb / 32.174) * gun_velocity ** 2


def estimate_powder(bullet_gr, muzzle_fps):
    """Rough powder charge (gr) from muzzle energy, for custom loads with no charge given."""
    return max(0.3, energy_ftlbs(bullet_gr, muzzle_fps) / 60.0)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
# Bullet diameter (inches) per cartridge, for Taylor KO. Shotshells aren't listed.
DIAMETERS = {
    ".22-250 Remington": .224, ".223 Remington": .224, ".223 Remington / 5.56 NATO": .224,
    ".224 Valkyrie": .224, ".243 Winchester": .243, ".25-35 Winchester": .257, "6mm ARC": .243,
    "6.5 Grendel": .264, ".260 Remington": .264, "6.5 Creedmoor": .264, "6.5 PRC": .264,
    ".270 Winchester": .277, "7mm-08 Remington": .284, ".277 Fury": .277, "6.8 Western": .277,
    "7mm Remington Magnum": .284, ".300 Blackout": .308, "7.62x39": .310, ".30-30 Winchester": .308,
    ".32-40 Winchester": .321, ".308 Winchester": .308, ".308 Winchester / 7.62x51 NATO": .308,
    ".30-06 Springfield": .308, ".300 Winchester Magnum": .308, ".300 PRC": .308,
    ".35 Remington": .358, ".348 Winchester": .348, ".350 Legend": .357, ".357 Magnum": .357,
    ".38-55 Winchester": .376, ".44 Magnum": .429, ".444 Marlin": .429, ".450 Bushmaster": .452,
    ".22 LR": .224, ".22 WMR": .224, ".25 ACP": .251, ".32 ACP": .312, ".32 H&R Magnum": .312,
    ".380 ACP": .355, "9mm Luger": .355, ".40 S&W": .400, "10mm Auto": .400, ".45 ACP": .451,
    ".38 Special": .357, ".45 Colt": .452, ".17 Mach 2": .172, ".17 HMR": .172, ".17 WSM": .172,
    ".22 Short": .224, ".22 Long": .224,
    # added later
    "5.45x39": 0.221,
    "6.5x55 Swedish": 0.264,
    "8x57 Mauser": 0.323,
    ".204 Ruger": 0.204,
    ".22 Hornet": 0.224,
    ".222 Remington": 0.224,
    ".220 Swift": 0.224,
    ".22 ARC": 0.224,
    ".22 Creedmoor": 0.224,
    ".25 Creedmoor": 0.257,
    "6mm Creedmoor": 0.243,
    ".25-06 Remington": 0.257,
    ".280 Remington": 0.284,
    ".270 WSM": 0.277,
    "7mm WSM": 0.284,
    "7mm PRC": 0.284,
    ".300 WSM": 0.308,
    ".338 Winchester Magnum": 0.338,
    ".338 Lapua Magnum": 0.338,
    ".338 ARC": 0.338,
    ".375 H&H Magnum": 0.375,
    ".375 Ruger": 0.375,
    ".416 Remington Magnum": 0.416,
    ".458 Winchester Magnum": 0.458,
    ".458 Lott": 0.458,
    ".45-70 Government": 0.458,
    ".30 Carbine": 0.308,
    "6.8mm SPC": 0.277,
    ".303 British": 0.311,
    ".300 Savage": 0.308,
    ".250 Savage": 0.257,
    ".257 Roberts": 0.257,
    ".35 Whelen": 0.358,
    ".358 Winchester": 0.358,
    ".50 BMG": 0.51,
    ".300 Weatherby Magnum": 0.308,
    ".300 Remington Ultra Mag": 0.308,
    "7mm STW": 0.284,
    ".28 Nosler": 0.284,
    ".30 Thompson/Center": 0.308,
    "6mm Remington": 0.243,
    "9.3x62": 0.366,
    ".30-40 Krag": 0.308,
    ".357 SIG": 0.355,
    ".41 Magnum": 0.41,
    ".44 Special": 0.429,
    ".454 Casull": 0.452,
    ".460 S&W Magnum": 0.452,
    ".480 Ruger": 0.475,
    "5.7x28": 0.224,
    ".50 AE": 0.5,
    ".500 S&W Magnum": 0.5,
    "9x18 Makarov": 0.365,
    ".327 Federal Magnum": 0.312,
    ".44-40 Winchester": 0.427,
    "7.62x54R": 0.311,
    "7.62x25 Tokarev": 0.309,
    ".38 Super": 0.355,
    ".32 S&W Long": 0.312,
}


def bullet_diameter(cartridge, bullet_gr):
    """Known diameter, else a guess from the weight (sectional density ~0.25). 0 = not applicable."""
    d = DIAMETERS.get(cartridge)
    if d:
        return d
    if "gauge" in cartridge.lower() or "bore" in cartridge.lower():
        return 0.0
    return min(0.6, max(0.17, math.sqrt(bullet_gr / 7000.0 / 0.25)))


def taylor_ko(bullet_gr, velocity_fps, diameter_in):
    """Taylor Knock-Out factor: bullet weight (gr) x velocity (fps) x diameter (in) / 7000."""
    return bullet_gr * velocity_fps * diameter_in / 7000.0


@dataclass
class Load:
    cartridge: str
    load: str
    bullet_gr: float               # bullet weight, or total shot payload for shotguns
    muzzle_fps: float
    bc_g1: float
    powder_gr: float
    default_cost: float
    is_default: bool = False       # preselected when the cartridge is chosen
    source: str = ""               # published / partial / approx / custom (informational)
    group: str = ""                # shotgun load type (Target, Buckshot, ...)
    barrel_in: float = 0.0         # test barrel length in inches (0 = not listed)
    purpose: str = ""              # Hunting / Varmint / Target / Match / Defense / Subsonic
    diameter_in: float = 0.0       # bullet diameter; 0 = look it up from the cartridge name
    label: str = ""                # text shown in the load dropdown
    handload: bool = False         # one of your own reloads (my_handloads.csv)
    hid: str = ""                  # handload id
    info: object = None            # handload record (bullet, powder, cost breakdown, notes)


def make_label(item, grain_style):
    if grain_style:
        base = f"{item.bullet_gr:g} gr"
        return f"{base}  ·  {item.load}" if item.load else base
    if item.group and item.load:
        return f"{item.group}  ·  {item.load}"
    return item.load or f"{item.bullet_gr:g} gr"


def app_dir():
    if getattr(sys, "frozen", False):              # packaged with PyInstaller
        return os.path.dirname(sys.executable)
    here = os.path.dirname(os.path.abspath(__file__))
    repo_data = os.path.join(os.path.dirname(here), "data")   # running from a git checkout
    return repo_data if os.path.isdir(repo_data) else here


def _opt_float(text):
    try:
        return max(0.0, float(text))
    except (TypeError, ValueError):
        return 0.0


def load_data(path, grain_style=True):
    """Read a CSV. Returns (loads, problems) where problems is a list of strings."""
    loads, problems = [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name = row.get("cartridge", "")
            if not name or name.startswith("#"):
                continue
            try:
                item = Load(
                    cartridge=name,
                    load=row.get("load", ""),
                    bullet_gr=float(row["bullet_gr"]),
                    muzzle_fps=float(row["muzzle_fps"]),
                    bc_g1=float(row["bc_g1"]),
                    powder_gr=float(row["powder_gr"]),
                    default_cost=float(row["default_cost"]),
                    is_default=row.get("default", "").lower() in ("yes", "y", "1", "true", "x"),
                    source=row.get("source", ""),
                    group=row.get("group", ""),
                    barrel_in=_opt_float(row.get("barrel_in", "")),
                    purpose=row.get("purpose", "") or row.get("group", ""),
                    diameter_in=_opt_float(row.get("diameter_in", "")),
                )
                if min(item.bullet_gr, item.muzzle_fps, item.bc_g1, item.powder_gr) <= 0:
                    raise ValueError("values must be positive")
                item.label = make_label(item, grain_style)
                loads.append(item)
            except (KeyError, ValueError) as exc:
                problems.append(f"Line {line_no} ({name}): {exc}")
    return loads, problems


def group_by_cartridge(loads, sort=True):
    """{cartridge: [loads]} keeping file order of cartridges; loads sorted by weight if asked."""
    groups = {}
    for item in loads:
        groups.setdefault(item.cartridge, []).append(item)
    if sort:
        for items in groups.values():
            items.sort(key=lambda x: (x.bullet_gr, x.load))
    return groups


def read_settings():
    try:
        with open(os.path.join(app_dir(), SETTINGS_FILENAME), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_settings(data):
    try:
        with open(os.path.join(app_dir(), SETTINGS_FILENAME), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass                                    # settings are a convenience, never fatal


# ---- user-added calibers (my_calibers.csv) ---- #
def custom_path():
    return os.path.join(app_dir(), CUSTOM_FILENAME)


def read_custom_rows():
    path = custom_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(fh)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def write_custom_rows(rows):
    with open(custom_path(), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CUSTOM_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_from_custom_row(row, grain_style=True):
    item = Load(
        cartridge=row["cartridge"],
        load=row.get("load") or "Custom",
        bullet_gr=float(row["bullet_gr"]),
        muzzle_fps=float(row["muzzle_fps"]),
        bc_g1=float(row["bc_g1"]),
        powder_gr=float(row["powder_gr"]),
        default_cost=float(row["default_cost"]),
        source="custom",
        diameter_in=_opt_float(row.get("diameter_in", "")),
    )
    if min(item.bullet_gr, item.muzzle_fps, item.bc_g1, item.powder_gr) <= 0:
        raise ValueError("values must be positive")
    item.label = make_label(item, grain_style)
    return item


# ---- handloads (my_handloads.csv) and the bullet library (bullets.csv) ---- #
def read_bullets():
    """Common bullets: [{maker, name, diameter, weight, bc, type}]. Empty if the file is missing."""
    path = os.path.join(app_dir(), BULLETS_FILENAME)
    out = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                try:
                    out.append(dict(maker=row["maker"].strip(), name=row["name"].strip(),
                                    diameter=float(row["diameter_in"]), weight=float(row["weight_gr"]),
                                    bc=float(row["bc_g1"]), type=row.get("type", "").strip()))
                except (KeyError, ValueError):
                    continue
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return out


def read_handload_rows():
    path = os.path.join(app_dir(), HANDLOAD_FILENAME)
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(fh)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def write_handload_rows(rows):
    with open(os.path.join(app_dir(), HANDLOAD_FILENAME), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HANDLOAD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def new_handload_id():
    import time
    import random
    return f"h{int(time.time() * 1000)}{random.randint(100, 999)}"


def handload_cost(bullet_cost=0.0, powder_cost_lb=0.0, powder_gr=0.0, primer_cost=0.0,
                  brass_cost=0.0, brass_reuse=5.0):
    """Cost of one round from its parts (brass cost is spread over the number of reloads)."""
    return (bullet_cost + powder_gr / 7000.0 * powder_cost_lb + primer_cost
            + brass_cost / max(1.0, brass_reuse))


def estimate_bc(bullet_gr, diameter_in, handgun=False):
    """Rough G1 BC from sectional density, for a bullet whose BC you don't know."""
    sd = bullet_gr / 7000.0 / diameter_in ** 2
    return round(sd * (0.95 if handgun else 1.7), 3)


def handload_label(row):
    name = row.get("name") or " ".join(x for x in (
        row.get("bullet_maker", ""), row.get("bullet", "")) if x) or "Handload"
    if not row.get("name"):
        name += f" {float(row['bullet_gr']):g} gr"
        if row.get("powder"):
            name += f" + {row['powder']} {float(row['powder_gr']):g} gr"
    return name


def load_from_handload_row(row, grain_style=True):
    item = Load(
        cartridge=row["cartridge"],
        load=handload_label(row),
        bullet_gr=float(row["bullet_gr"]),
        muzzle_fps=float(row["muzzle_fps"]),
        bc_g1=float(row["bc_g1"]),
        powder_gr=float(row["powder_gr"]),
        default_cost=float(row["cost"]),
        source="handload",
        barrel_in=_opt_float(row.get("barrel_in", "")),
        purpose=row.get("purpose", ""),
        diameter_in=_opt_float(row.get("diameter_in", "")),
        handload=True, hid=row.get("id", ""), info=dict(row),
    )
    if min(item.bullet_gr, item.muzzle_fps, item.bc_g1, item.powder_gr, item.default_cost) <= 0:
        raise ValueError("values must be positive")
    item.label = make_label(item, grain_style)
    return item


def same_custom_row(row, item):
    return (row.get("cartridge") == item.cartridge
            and (row.get("load") or "Custom") == item.load
            and abs(float(row.get("bullet_gr") or 0) - item.bullet_gr) < 1e-6
            and abs(float(row.get("muzzle_fps") or 0) - item.muzzle_fps) < 1e-6)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def compute_stats(item, distance_yd, gun_lb, cost=None):
    v = velocity_at(item.muzzle_fps, item.bc_g1, distance_yd)
    d = item.diameter_in or bullet_diameter(item.cartridge, item.bullet_gr)
    return {
        "weight": item.bullet_gr,
        "velocity": v,
        "energy": energy_ftlbs(item.bullet_gr, v),
        "recoil": recoil_ftlbs(item.bullet_gr, item.muzzle_fps, item.powder_gr, gun_lb),
        "cost": item.default_cost if cost is None else cost,
        "taylor": taylor_ko(item.bullet_gr, v, d),
    }


def reference_levels(loads, distance_yd, gun_lb):
    """The 'typical' (median) value of each factor across the category's loads."""
    all_stats = [compute_stats(x, distance_yd, gun_lb) for x in loads]
    return {k: statistics.median(s[k] for s in all_stats) for k in METRICS}


# "Compare Loads" grades loads of the SAME cartridge against each other. They are all close
# to the category's typical load, so scores are spread out relative to the group: the average
# load of the cartridge scores REL_CENTER and each standard deviation moves it REL_SPREAD points.
REL_CENTER, REL_SPREAD = 70.0, 10.0
REL_BANDS = [(85, "S"), (77, "A"), (66, "B"), (55, "C"), (45, "D")]


def grade_relative(score):
    for threshold, letter in REL_BANDS:
        if score >= threshold:
            return letter
    return "F"


def _spread(values):
    """Map raw numbers to REL_CENTER +/- REL_SPREAD per 'typical spread' (clipped 0-100).

    Uses the median and the median absolute deviation, so one odd load (say a subsonic
    round among supersonic ones) doesn't squash everyone else's scores together.
    """
    n = len(values)
    mid = statistics.median(values)
    scale = 1.4826 * statistics.median(abs(v - mid) for v in values)
    if scale < 1e-9:
        mean = sum(values) / n
        scale = math.sqrt(sum((v - mean) ** 2 for v in values) / n) if n > 1 else 0.0
        mid = mean
    if scale < 1e-9:
        return [REL_CENTER] * n
    return [min(100.0, max(0.0, REL_CENTER + REL_SPREAD * (v - mid) / scale)) for v in values]


def relative_scores(stats_list, weights):
    """stats_list: stats dicts (compute_stats) for every load of one cartridge.
    Returns [(per-metric scores, overall)] on the within-cartridge scale."""
    if not stats_list:
        return []
    refs = {k: statistics.median(s[k] for s in stats_list) for k in METRICS}
    per = {k: _spread([metric_score(s[k], refs[k], METRICS[k][1]) for s in stats_list])
           for k in METRICS}
    total_w = sum(weights.values())
    w = weights if total_w > 0 else {k: 1.0 for k in METRICS}
    total_w = sum(w.values())
    raw = [sum(per[k][i] * w[k] for k in METRICS) / total_w for i in range(len(stats_list))]
    overall = _spread(raw)
    return [({k: per[k][i] for k in METRICS}, overall[i]) for i in range(len(stats_list))]


def rank_among(item, overall, loads, dist, gun, weights, refs):
    """(rank within the item's cartridge, cartridge size, rank in category, category size).

    Everyone is compared at their default price so the ranking doesn't move when you
    type a different price for one load; rank 1 = best.
    """
    scores = []
    for other in loads:
        _, o = score_stats(compute_stats(other, dist, gun), refs, weights)
        scores.append((other, o))
    in_cart = [o for x, o in scores if x.cartridge == item.cartridge and x is not item]
    others = [o for x, o in scores if x is not item]
    return (1 + sum(o > overall for o in in_cart), len(in_cart) + 1,
            1 + sum(o > overall for o in others), len(others) + 1)


def grade_for(score):
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


def metric_score(value, ref, higher_better):
    """Score one factor 0-100 on a curve; `ref` is the category's typical value.

    Higher-is-better (velocity, energy): 100 * (1 - e^(-k*x)), so each extra bit
    helps less than the last and absurd values stop paying off.
    Lower-is-better (recoil, cost): 100 * e^(-k*x), so cheaper/softer keeps
    helping but a high price or recoil never drops straight to zero.
    """
    if ref <= 0:
        return 50.0
    x = max(value, 0.0) / ref
    if higher_better:
        return 100.0 * (1.0 - math.exp(-_HIGH_K * x))
    return 100.0 * math.exp(-_LOW_K * x)


def score_stats(stats, refs, weights):
    """Returns (per-metric scores, overall score), all 0-100."""
    scores = {k: metric_score(stats[k], refs[k], METRICS[k][1]) for k in METRICS}
    total_w = sum(weights.values())
    if total_w <= 0:
        weights = {k: 1.0 for k in METRICS}
        total_w = float(len(METRICS))
    overall = sum(scores[k] * weights[k] for k in METRICS) / total_w
    return scores, overall


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class App:
    """Owns the window, the theme, and switching between the picker and calculators."""

    CALC_MIN_WIDTH = 700          # (kept for compatibility)
    LOADS_MIN_WIDTH = 960
    WIN_W, WIN_H = 1360, 860      # default window size (clamped to small screens); resizable
    MIN_W, MIN_H = 980, 600
    SIDEBAR_W = 210

    def __init__(self, root):
        self.root = root
        self.settings = read_settings()
        try:
            self.scale = min(1.6, max(0.85, float(self.settings.get("text_scale", 1.0))))
        except (TypeError, ValueError):
            self.scale = 1.0
        self.view = None
        families = set(tkfont.families(root))
        self.family = next((f for f in ("Segoe UI", "SF Pro Text", "Inter", "Noto Sans",
                                        "Cantarell", "Ubuntu", "Helvetica Neue", "Helvetica",
                                        "Arial", "DejaVu Sans") if f in families), "TkDefaultFont")
        root.configure(bg=BG)
        self._style()

        # load every category's data up front so the picker can show counts
        self.data = {}      # title -> dict(loads=[...], problems=[...], error="")
        self.hand_rows = read_handload_rows()
        self.bullets = read_bullets()
        custom_rows = read_custom_rows()
        for cat in CATEGORIES:
            self.data[cat.title] = self._load_category(cat, custom_rows)

        self.stage = None
        self.mode = "home"                # home / cartridges / loads
        self.cat = None
        self.carry = {}                   # per category: what each tab knew when you left it
        last = self.settings.get("last_category")
        self.last_cat = next((c for c in CATEGORIES if c.title == last), CATEGORIES[0])
        self._place_window()
        self._build_shell()
        self.show_launcher()
        root.bind_all("<Control-Key-1>", lambda e: self.go_mode("cartridges"))
        root.bind_all("<Control-Key-2>", lambda e: self.go_mode("loads"))
        root.bind_all("<Control-Key-0>", lambda e: self.show_launcher())

    # ---- data ------------------------------------------------------------ #
    def _load_category(self, cat, custom_rows):
        names = [cat.filename] + ([cat.legacy_filename] if cat.legacy_filename else [])
        path = next((p for p in (os.path.join(app_dir(), n) for n in names)
                     if os.path.exists(p)), None)
        if path is None:
            return {"loads": [], "problems": [], "error": f"{cat.filename} not found", "detail": [], "detail_error": ""}
        try:
            loads, problems = load_data(path, cat.grain_style)
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            return {"loads": [], "problems": [], "error": f"Could not read {cat.filename}: {exc}", "detail": [], "detail_error": ""}
        if not loads:
            return {"loads": [], "problems": problems, "error": f"{cat.filename} has no usable rows", "detail": [], "detail_error": ""}
        if cat.allow_custom:
            for row in custom_rows:
                if row.get("category") != cat.title:
                    continue
                try:
                    loads.append(load_from_custom_row(row, cat.grain_style))
                except (KeyError, ValueError) as exc:
                    problems.append(f"{CUSTOM_FILENAME} ({row.get('cartridge', '?')}): {exc}")
        detail, detail_error = [], ""
        if cat.loads_filename:
            dpath = os.path.join(app_dir(), cat.loads_filename)
            if not os.path.exists(dpath):
                detail_error = f"{cat.loads_filename} not found"
            else:
                try:
                    detail, dprob = load_data(dpath, cat.grain_style)
                    problems += [f"{cat.loads_filename}: {x}" for x in dprob]
                except (OSError, csv.Error, UnicodeDecodeError) as exc:
                    detail_error = f"Could not read {cat.loads_filename}: {exc}"
        return {"loads": loads, "problems": problems, "error": "", "detail": detail,
                "detail_error": detail_error}

    # ---- handloads --------------------------------------------------------- #
    def hand_loads(self, cat):
        out = []
        if not cat.grain_style:
            return out
        for row in self.hand_rows:
            if row.get("category") != cat.title:
                continue
            try:
                out.append(load_from_handload_row(row, cat.grain_style))
            except (KeyError, ValueError):
                continue
        return out

    def save_handload(self, row):
        """Add a handload record, or replace the one with the same id. May raise OSError."""
        rows = [dict(r) for r in self.hand_rows]
        for i, r in enumerate(rows):
            if r.get("id") == row["id"]:
                rows[i] = row
                break
        else:
            rows.append(row)
        write_handload_rows(rows)
        self.hand_rows = rows

    def delete_handload(self, hid):
        rows = [r for r in self.hand_rows if r.get("id") != hid]
        write_handload_rows(rows)
        self.hand_rows = rows

    # ---- prices you set yourself (Compare Loads tab) ---------------------- #
    @staticmethod
    def price_key(cat, item):
        return f"{cat.title}|{item.cartridge}|{item.label}"

    def price_for(self, cat, item):
        try:
            return float(self.settings.get("prices", {}).get(self.price_key(cat, item), item.default_cost))
        except (TypeError, ValueError):
            return item.default_cost

    def set_price(self, cat, item, value):
        prices = self.settings.setdefault("prices", {})
        if value is None or abs(value - item.default_cost) < 1e-9:
            prices.pop(self.price_key(cat, item), None)
        else:
            prices[self.price_key(cat, item)] = round(value, 4)
        write_settings(self.settings)

    # ---- styling --------------------------------------------------------- #
    def f(self, size, bold=False):
        return (self.family, max(7, int(round(size * self.scale))), "bold" if bold else "normal")

    def px(self, n):
        """Scale a pixel measurement with the text size."""
        return int(round(n * self.scale))

    def set_scale(self, new_scale):
        """Text size A- / A+. Rebuilds the current screen and keeps what was entered."""
        new_scale = round(min(1.6, max(0.85, new_scale)), 2)
        if new_scale == self.scale:
            return
        self.scale = new_scale
        self.settings["text_scale"] = new_scale
        write_settings(self.settings)
        snap = self.view.snapshot() if self.view is not None else None
        cat = self.view.cat if self.view is not None else None
        tab = getattr(self.view, "tab", "cartridges")
        self._style()
        self._build_shell()                          # sidebar / tabs pick up the new size too
        if cat is None:
            if self.mode == "home":
                self.show_launcher()
            else:
                self.show_picker(self.mode)
        else:
            self.open_category(cat, tab)
            if snap:
                self.view.restore(snap)

    def size_controls(self, parent, bg):
        """Small 'Text size  A-  A+' control, packed by the caller."""
        box = tk.Frame(parent, bg=bg)
        tk.Label(box, text="Text size", bg=bg, fg=MUTED, font=self.f(9)).pack(side="left", padx=(0, 6))
        for text, delta in (("A−", -0.15), ("A+", 0.15)):
            b = tk.Label(box, text=text, bg=SURFACE_2, fg=TEXT, font=self.f(10, True),
                         padx=10, pady=3, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, d=delta: self.set_scale(self.scale + d))
        return box

    def _style(self):
        r = self.root
        s = ttk.Style(r)
        s.theme_use("clam")
        r.option_add("*TCombobox*Listbox.background", SURFACE_2)
        r.option_add("*TCombobox*Listbox.foreground", TEXT)
        r.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        r.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        r.option_add("*TCombobox*Listbox.font", self.f(11))
        field = dict(fieldbackground=SURFACE_2, background=SURFACE_2, foreground=TEXT,
                     bordercolor=BORDER, lightcolor=SURFACE_2, darkcolor=SURFACE_2,
                     arrowcolor=MUTED, insertcolor=TEXT, padding=6)
        for name in ("TCombobox", "TEntry", "TSpinbox"):
            s.configure(name, **field)
        s.map("TCombobox",
              fieldbackground=[("readonly", SURFACE_2)],
              foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", SURFACE_2)],
              selectforeground=[("readonly", TEXT)],
              bordercolor=[("focus", ACCENT)],
              arrowcolor=[("active", TEXT)])
        s.map("TEntry", bordercolor=[("focus", ACCENT)])
        s.map("TSpinbox", bordercolor=[("focus", ACCENT)], arrowcolor=[("active", TEXT)])
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    bordercolor=BORDER, rowheight=self.px(28), font=self.f(10))
        s.configure("Treeview.Heading", background=SURFACE_2, foreground=TEXT,
                    relief="flat", font=self.f(10, True), padding=6)
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        s.map("Treeview.Heading", background=[("active", BORDER)])

    def label(self, parent, text="", size=11, color=TEXT, bold=False, bg=SURFACE, **kw):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=self.f(size, bold), **kw)

    def button(self, parent, text, command, kind="secondary"):
        if kind == "primary":
            bg, fg, hover = ACCENT, "#ffffff", ACCENT_HOVER
        else:
            bg, fg, hover = SURFACE_2, TEXT, BORDER
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                      activeforeground=fg, relief="flat", bd=0, highlightthickness=0,
                      font=self.f(11, True), padx=16, pady=8, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def fit_columns(self, tree, cols, rows, stretch_col, known=None):
        """Size table columns from the real text width (fonts grow with screen DPI, pixel
        counts don't). `rows` are lists of cell strings; `known` keeps widths from earlier
        calls so columns never shrink while filtering. The stretch column takes spare room."""
        head = tkfont.Font(font=self.f(10, True))
        body = tkfont.Font(font=self.f(10))
        pad = body.measure("00") + 14
        known = {} if known is None else known
        for i, col in enumerate(cols):
            need = max([head.measure(col)] + [body.measure(str(r[i])) for r in rows]) + pad
            if col == stretch_col:
                # wide enough for most names; very long ones are cut rather than widening the table
                need = min(need, body.measure("0" * 44))
            known[col] = max(known.get(col, 0), need)
            if col == stretch_col:
                tree.column(col, width=known[col], minwidth=min(known[col], body.measure("0" * 24)),
                            stretch=True)
            else:
                tree.column(col, width=known[col], minwidth=known[col], stretch=False)
        return known

    def grow_to_fit(self, extra):
        """Widen the window by `extra` px (to fit a table), within the screen. Never shrinks."""
        r = self.root
        if extra <= 0 or r.state() == "zoomed":
            return
        w = min(r.winfo_width() + extra, r.winfo_screenwidth() - 20)
        if w > r.winfo_width():
            x = max(0, min(r.winfo_x(), r.winfo_screenwidth() - w - 10))
            r.geometry(f"{w}x{r.winfo_height()}+{x}+{r.winfo_y()}")

    # ---- window + shell --------------------------------------------------- #
    def _place_window(self):
        """Comfortable default size, centred; the window can be resized from there."""
        r = self.root
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w, h = min(self.WIN_W, sw - 40), min(self.WIN_H, sh - 90)
        r.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        r.minsize(min(self.MIN_W, w), min(self.MIN_H, h))
        r.resizable(True, True)
        r.title(APP_TITLE)

    def fit_window(self, min_width=0, keep_position=False):
        """The window keeps its size; the page scrolls if it is taller. Refresh the scroll area."""
        self._update_scroll()

    def _update_scroll(self):
        try:
            self.root.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            need = self.stage.winfo_reqheight() > self.canvas.winfo_height() + 1
            shown = self.vbar.winfo_ismapped()
            if need and not shown:
                self.vbar.pack(side="right", fill="y", before=self.canvas)
            elif not need and shown:
                self.vbar.pack_forget()
        except Exception:
            pass

    def _build_shell(self):
        """Sidebar (always visible) + a scrolling page."""
        if getattr(self, "shell", None) is not None:
            self.shell.destroy()
        self.shell = tk.Frame(self.root, bg=BG)
        self.shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(self.shell, bg=SURFACE, width=self._sidebar_width())
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Frame(self.shell, bg=BORDER, width=1).pack(side="left", fill="y")
        foot = tk.Frame(self.sidebar, bg=SURFACE)
        foot.pack(side="bottom", fill="x", padx=14, pady=14)
        self.size_controls(foot, SURFACE).pack(anchor="w")
        self.nav = tk.Frame(self.sidebar, bg=SURFACE)
        self.nav.pack(fill="x", padx=12, pady=(22, 0))

        self.main = tk.Frame(self.shell, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        scroll_box = tk.Frame(self.main, bg=BG)
        scroll_box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll_box, bg=BG, highlightthickness=0)
        self.vbar = ttk.Scrollbar(scroll_box, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.stage = tk.Frame(self.canvas, bg=BG)
        win_id = self.canvas.create_window((0, 0), window=self.stage, anchor="nw")
        self.stage.bind("<Configure>", lambda e: self._update_scroll())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(win_id, width=e.width),
                                                   self._update_scroll()))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._on_wheel)
        self._draw_chrome()

    def _sidebar_width(self):
        """Wide enough for the longest menu entry at the current text size and screen DPI."""
        main, sub = tkfont.Font(font=self.f(11, True)), tkfont.Font(font=self.f(10, True))
        need = max([main.measure("Compare Cartridges")]
                   + [sub.measure(cat.title) + 16 for cat in CATEGORIES])
        return max(self.px(self.SIDEBAR_W), need + 2 * 12 + 2 * 12 + 10)   # label + nav padding

    def _on_wheel(self, e):
        """Scroll the page with the mouse wheel (tables and lists keep their own wheel)."""
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except Exception:
            w = None
        while w is not None:
            if isinstance(w, (ttk.Treeview, tk.Listbox)):
                return
            w = getattr(w, "master", None)
        if self.stage.winfo_reqheight() <= self.canvas.winfo_height():
            return
        step = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        self.canvas.yview_scroll(step * 3, "units")

    def _nav_button(self, text, command, active, sub=False):
        bg = ACCENT if active else (SURFACE_2 if sub and False else SURFACE)
        hover = ACCENT if active else SURFACE_2
        fg = "#ffffff" if active else (MUTED if sub else TEXT)
        box = tk.Frame(self.nav, bg=bg, cursor="hand2")
        box.pack(fill="x", pady=(1 if sub else 3), padx=(16, 0) if sub else (0, 0))
        t = tk.Label(box, text=text, bg=bg, fg=fg, font=self.f(10 if sub else 11, not sub or active),
                     anchor="w")
        t.pack(fill="x", padx=12, pady=(6 if sub else 9))
        for w in (box, t):
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: [x.config(bg=hover) for x in (box, t)])
            w.bind("<Leave>", lambda e: [x.config(bg=bg) for x in (box, t)])
        return box

    def _draw_chrome(self):
        """(Re)draw the sidebar: Home, the two features, and the categories of the open feature."""
        for w in self.nav.winfo_children():
            w.destroy()
        self.label(self.nav, "Cartridge\nCalculator", 15, TEXT, True, bg=SURFACE,
                   anchor="w", justify="left").pack(anchor="w", padx=6, pady=(0, 18))
        self._nav_button("Home", self.show_launcher, self.mode == "home")
        for key, text in (("cartridges", "Compare Cartridges"), ("loads", "Compare Loads")):
            on_picker = self.mode == key and self.cat is None
            self._nav_button(text, lambda k=key: self.show_picker(k), on_picker)
            if self.mode == key:
                for cat in CATEGORIES:
                    on = self.cat is not None and cat.title == self.cat.title
                    self._nav_button(cat.title, lambda c=cat, k=key: self.go(c, k), on, sub=True)

    # ---- screens --------------------------------------------------------- #
    def _new_stage(self):
        self.root.unbind("<Return>")
        for w in self.stage.winfo_children():
            w.destroy()
        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass
        return self.stage

    def _card_hover(self, widgets, base, hover):
        for w in widgets:
            w.bind("<Enter>", lambda e: [x.config(bg=hover) for x in widgets])
            w.bind("<Leave>", lambda e: [x.config(bg=base) for x in widgets])

    def show_launcher(self):
        """Home screen: the two things you can do."""
        self.mode, self.cat, self.view = "home", None, None
        stage = self._new_stage()
        self.root.title(APP_TITLE)
        self._draw_chrome()
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="x", padx=36, pady=(40, 28))
        self.label(wrap, "Cartridge Calculator", 26, TEXT, True, bg=BG, anchor="w").pack(anchor="w")
        self.label(wrap, "Grade ammo from S to F on velocity, energy, recoil and cost.", 12, MUTED,
                   bg=BG, anchor="w").pack(anchor="w", pady=(4, 26))
        feats = tk.Frame(wrap, bg=BG)
        feats.pack(fill="x")
        feats.columnconfigure((0, 1), weight=1, uniform="f")
        for i, (key, title, blurb) in enumerate((
                ("cartridges", "Compare Cartridges", "Which caliber is the best value?"),
                ("loads", "Compare Loads", "Which load is best, factory or your own handload?"))):
            card = tk.Frame(feats, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                            cursor="hand2")
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 8 if i == 0 else 0))
            t = tk.Label(card, text=title, bg=SURFACE, fg=TEXT, font=self.f(17, True), anchor="w",
                         cursor="hand2")
            t.pack(fill="x", padx=24, pady=(26, 4))
            d = tk.Label(card, text=blurb, bg=SURFACE, fg=MUTED, font=self.f(11), anchor="w",
                         justify="left", wraplength=self.px(330), cursor="hand2")
            d.pack(fill="x", padx=24, pady=(0, 26))
            for w in (card, t, d):
                w.bind("<Button-1>", lambda e, k=key: self.show_picker(k))
            self._card_hover([card, t, d], SURFACE, SURFACE_2)
        self._update_scroll()

    def show_picker(self, mode):
        """Choose a category for the feature (Compare Cartridges or Compare Loads)."""
        if self.view is not None and self.cat is not None:
            self.carry.setdefault(self.cat.title, {}).update(self.view.snapshot())
        self.mode, self.cat, self.view = mode, None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {'Compare Cartridges' if mode == 'cartridges' else 'Compare Loads'}")
        self._draw_chrome()
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="x", padx=36, pady=(32, 28))
        self.label(wrap, "Compare Cartridges" if mode == "cartridges" else "Compare Loads", 22,
                   TEXT, True, bg=BG, anchor="w").pack(anchor="w")
        self.label(wrap, "Choose a category", 12, MUTED, bg=BG, anchor="w").pack(
            anchor="w", pady=(2, 20))
        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="g")
        for i, cat in enumerate(CATEGORIES):
            info = self.data[cat.title]
            if info["error"]:
                caption = "Data file missing" if "not found" in info["error"] else "Data problem"
            else:
                n = len(info["detail"]) if mode == "loads" and info["detail"] else len(info["loads"])
                caption = (f"{len({x.cartridge for x in info['loads']})} cartridges  ·  "
                           f"{len(info['detail']) or len(info['loads'])} loads")
            card = tk.Frame(grid, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                            cursor="hand2")
            card.grid(row=i // 2, column=i % 2, sticky="nsew", pady=6,
                      padx=(0 if i % 2 == 0 else 6, 6 if i % 2 == 0 else 0))
            t = tk.Label(card, text=cat.title, bg=SURFACE, fg=TEXT, font=self.f(15, True),
                         anchor="w", cursor="hand2")
            t.pack(fill="x", padx=22, pady=(20, 2))
            c = tk.Label(card, text=caption, bg=SURFACE, fg=ACCENT, font=self.f(10, True),
                         anchor="w", cursor="hand2")
            c.pack(fill="x", padx=22)
            d = tk.Label(card, text=cat.blurb, bg=SURFACE, fg=MUTED, font=self.f(10), anchor="w",
                         cursor="hand2")
            d.pack(fill="x", padx=22, pady=(4, 20))
            for w in (card, t, c, d):
                w.bind("<Button-1>", lambda e, ct=cat: self.go(ct, mode))
            self._card_hover([card, t, c, d], SURFACE, SURFACE_2)
        self._update_scroll()

    def header(self, parent, cat, active):
        """Back link and the page title."""
        box = tk.Frame(parent, bg=BG)
        back = tk.Label(box, text="‹  Categories", bg=BG, fg=MUTED, font=self.f(10, True),
                        cursor="hand2")
        back.grid(row=0, column=0, sticky="w")
        back.bind("<Button-1>", lambda e: self.show_picker(active))
        back.bind("<Enter>", lambda e: back.config(fg=TEXT))
        back.bind("<Leave>", lambda e: back.config(fg=MUTED))
        title = "Compare Cartridges" if active == "cartridges" else "Compare Loads"
        self.label(box, f"{title}  ·  {cat.title}", 20, TEXT, True, bg=BG).grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        return box

    def go(self, cat, tab):
        """Open a category in a feature, remembering what each tab had on screen."""
        if self.view is not None and self.cat is not None:
            self.carry.setdefault(self.cat.title, {}).update(self.view.snapshot())
        self.open_category(cat, tab)
        mem = self.carry.get(cat.title)
        if mem and self.view is not None:
            self.view.restore(dict(mem))

    def go_mode(self, tab):
        self.show_picker(tab)

    switch_tab = go

    def open_category(self, cat, tab="cartridges"):
        info = self.data[cat.title]
        if info["error"]:
            messagebox.showerror("Can't open this category", info["error"] +
                                 f"\n\nExpected next to the program:\n{app_dir()}")
            return
        if info["problems"]:
            messagebox.showwarning("Some rows were skipped", "\n".join(info["problems"][:15]))
            info["problems"] = []                   # only warn once
        self.cat, self.mode, self.last_cat = cat, tab, cat
        if self.settings.get("last_category") != cat.title:
            self.settings["last_category"] = cat.title
            write_settings(self.settings)
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {cat.title}")
        self._draw_chrome()
        if tab == "loads":
            self.view = LoadsView(self, stage, cat, info["detail"] + self.hand_loads(cat),
                                  info["detail_error"])
        else:
            self.view = CalculatorView(self, stage, cat, info["loads"])
        self._update_scroll()


class CalculatorView:
    tab = "cartridges"

    def __init__(self, app, stage, cat, loads):
        self.app = app
        self.root = app.root
        self.cat = cat
        self.loads = loads                  # shared with App.data so custom loads persist
        self._regroup()
        self.label_to_load = {}            # load-dropdown text -> Load

        self.cart_var = tk.StringVar(value="")
        self.grain_var = tk.StringVar(value="")
        self.cost_var = tk.StringVar(value="")
        self.dist_var = tk.StringVar(value=f"{cat.default_distance:g}")
        self.gun_var = tk.StringVar(value=f"{cat.default_gun_lb:g}")
        self.weight_vars = {k: tk.StringVar(value=str(v)) for k, v in default_weights(cat).items()}
        self.weights_open = False
        self.keys = metric_keys(cat)

        self._build_ui(stage)
        for var in self.weight_vars.values():
            var.trace_add("write", self._refresh_weight_note)
        self._refresh_weight_note()
        self.root.bind("<Return>", lambda e: self.calculate())

    def snapshot(self):
        return dict(cart=self.cart_var.get(), grain=self.grain_var.get(), cost=self.cost_var.get(),
                    dist=self.dist_var.get(), gun=self.gun_var.get(),
                    weights={k: v.get() for k, v in self.weight_vars.items()},
                    weights_open=self.weights_open, had_result=self._last_overall is not None)

    def restore(self, snap):
        for k, v in snap.get("weights", {}).items():
            if k in self.weight_vars:
                self.weight_vars[k].set(v)
        if "dist" in snap:
            self.dist_var.set(snap["dist"])
        if "gun" in snap:
            self.gun_var.set(snap["gun"])
        if snap.get("cart") in self.groups:
            self.cart_var.set(snap["cart"])
            self._on_cartridge()
            if snap.get("grain") in self.label_to_load:
                self.grain_var.set(snap["grain"])
                self._on_grain()
            if snap.get("cost"):
                self.cost_var.set(snap["cost"])
        if snap.get("weights_open") and not self.weights_open:
            self._toggle_weights()
        if snap.get("had_result") and self._selected_load() is not None:
            self.calculate(quiet=True)

    def _regroup(self):
        self.groups = group_by_cartridge(self.loads, self.cat.sort_loads)
        self.cartridges = list(self.groups)

    # ---- layout ---------------------------------------------------------- #
    def _build_ui(self, stage):
        a, cat = self.app, self.cat
        outer = tk.Frame(stage, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        outer.columnconfigure(0, weight=1)

        a.header(outer, cat, "cartridges").grid(row=0, column=0, sticky="ew", pady=(0, 16))

        # ---- inputs card
        card = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=3, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        pad = dict(padx=18)

        a.label(card, cat.cartridge_label, 9, MUTED, True).grid(row=0, column=0, sticky="w",
                                                                 pady=(16, 4), **pad)
        self.cart_combo = ttk.Combobox(card, textvariable=self.cart_var, values=self.cartridges,
                                       state="readonly", font=a.f(12))
        self.cart_combo.grid(row=1, column=0, sticky="ew", **pad)
        self.cart_combo.bind("<<ComboboxSelected>>", lambda e: self._on_cartridge())

        # load dropdown: created now, shown only after a cartridge is chosen
        self.grain_frame = tk.Frame(card, bg=SURFACE)
        self.grain_frame.columnconfigure(0, weight=1)
        a.label(self.grain_frame, cat.load_label, 9, MUTED, True).grid(
            row=0, column=0, sticky="w", pady=(14, 4))
        self.grain_combo = ttk.Combobox(self.grain_frame, textvariable=self.grain_var,
                                        state="readonly", font=a.f(12))
        self.grain_combo.grid(row=1, column=0, sticky="ew")
        self.grain_combo.bind("<<ComboboxSelected>>", lambda e: self._on_grain())
        self.remove_link = tk.Label(self.grain_frame, text="Remove this custom load", bg=SURFACE,
                                    fg=MUTED, font=a.f(9), cursor="hand2")
        self.remove_link.bind("<Button-1>", lambda e: self._remove_custom())
        self.remove_link.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.remove_link.grid_remove()
        self.grain_frame.grid(row=2, column=0, sticky="ew", **pad)
        self.grain_frame.grid_remove()

        nums = tk.Frame(card, bg=SURFACE)
        nums.grid(row=3, column=0, sticky="ew", pady=(14, 0), **pad)
        for i in range(3):
            nums.columnconfigure(i, weight=1, uniform="n")
        for i, (text, var) in enumerate((("COST PER ROUND ($)", self.cost_var),
                                         ("DISTANCE (YD)", self.dist_var),
                                         (cat.gun_label, self.gun_var))):
            a.label(nums, text, 9, MUTED, True).grid(row=0, column=i, sticky="w",
                                                     padx=(0 if i == 0 else 8, 0))
            ttk.Entry(nums, textvariable=var, width=10, font=a.f(12)).grid(
                row=1, column=i, sticky="ew", pady=(4, 0), padx=(0 if i == 0 else 8, 0))

        # one quiet row of links: scoring weights (left), add your own caliber (right)
        links = tk.Frame(card, bg=SURFACE)
        links.grid(row=4, column=0, sticky="ew", pady=(14, 0), **pad)
        self.weights_toggle = tk.Label(links, text="▸  Scoring weights", bg=SURFACE, fg=MUTED,
                                       font=a.f(10, True), cursor="hand2")
        self.weights_toggle.pack(side="left")
        self.weights_toggle.bind("<Button-1>", lambda e: self._toggle_weights())
        if cat.allow_custom:
            add = tk.Label(links, text="+  Add your own caliber", bg=SURFACE, fg=ACCENT,
                           font=a.f(10, True), cursor="hand2")
            add.pack(side="right")
            add.bind("<Button-1>", lambda e: self._open_add_dialog())

        self.weights_frame = tk.Frame(card, bg=SURFACE)
        for i, key in enumerate(self.keys):
            a.label(self.weights_frame, METRICS[key][0], 10, MUTED).grid(
                row=0, column=i * 2, padx=(0 if i == 0 else 14, 6))
            ttk.Spinbox(self.weights_frame, from_=0, to=10, increment=1, width=3,
                        textvariable=self.weight_vars[key], font=a.f(11)).grid(
                row=0, column=i * 2 + 1)
        self.weight_note = a.label(self.weights_frame, "", 9, TEXT, True)
        self.weight_note.grid(row=1, column=0, columnspan=12, sticky="w", pady=(8, 0))
        a.label(self.weights_frame, "Higher = matters more. 0 ignores that factor."
                + ("  Taylor KO starts at 0 (shown, but not graded)." if cat.terminal else ""),
                9, MUTED).grid(row=2, column=0, columnspan=12, sticky="w", pady=(2, 0))
        self.weights_frame.grid(row=5, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_frame.grid_remove()

        btns = tk.Frame(card, bg=SURFACE)
        btns.grid(row=6, column=0, sticky="w", pady=(16, 18), **pad)
        a.button(btns, "Calculate", self.calculate, "primary").pack(side="left")
        a.button(btns, "Compare All", self.compare_all).pack(side="left", padx=8)
        a.button(btns, "Reset", self.reset).pack(side="left")

        # ---- result card (hidden until first calculation)
        self.result = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.result.columnconfigure(0, weight=1)
        self.res_title = a.label(self.result, "", 15, TEXT, True, anchor="w", justify="left",
                                 wraplength=a.px(600))
        self.res_title.grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(16, 0))
        self.res_sub = a.label(self.result, "", 10, MUTED, anchor="w")
        self.res_sub.grid(row=1, column=0, columnspan=3, sticky="w", padx=18, pady=(2, 10))

        self.res_values, self.res_badges = {}, {}
        rows = [("weight", cat.payload_row), ("velocity", "Velocity"), ("energy", "Energy"),
                ("recoil", "Recoil"), ("cost", "Cost")]
        if cat.terminal:
            rows += [("taylor", "Taylor KO")]
        for i, (key, text) in enumerate(rows, start=2):
            a.label(self.result, text, 11, MUTED).grid(row=i, column=0, sticky="w",
                                                       padx=(18, 8), pady=3)
            val = a.label(self.result, "", 12, TEXT, True)
            val.grid(row=i, column=1, sticky="e", padx=8, pady=3)
            self.res_values[key] = val
            if key in METRICS:
                badge = tk.Label(self.result, text="", width=3, font=a.f(10, True))
                badge.grid(row=i, column=2, sticky="e", padx=(8, 18), pady=3)
                self.res_badges[key] = badge

        r0 = 2 + len(rows)
        tk.Frame(self.result, bg=BORDER, height=1).grid(row=r0, column=0, columnspan=3,
                                                         sticky="ew", padx=18, pady=(8, 8))
        a.label(self.result, "Overall", 11, MUTED).grid(row=r0 + 1, column=0, sticky="w", padx=18)
        self.res_overall = a.label(self.result, "", 14, TEXT, True)
        self.res_overall.grid(row=r0 + 1, column=1, columnspan=2, sticky="e", padx=18)
        self.bar = tk.Canvas(self.result, height=22, bg=SURFACE, highlightthickness=0)
        self.bar.grid(row=r0 + 2, column=0, columnspan=3, sticky="ew", padx=18, pady=(8, 4))
        self.res_rank = a.label(self.result, "", 10, TEXT, anchor="w", justify="left",
                                wraplength=a.px(600))
        self.res_rank.grid(row=r0 + 3, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 0))
        self.res_note = a.label(self.result, "", 9, MUTED, anchor="w", justify="left",
                                wraplength=a.px(600))
        self.res_note.grid(row=r0 + 4, column=0, columnspan=3, sticky="w", padx=18, pady=(6, 16))
        self.result.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        self.result.grid_remove()
        self._last_overall = None
        self.bar.bind("<Configure>", lambda e: self._draw_bar())

    # ---- small helpers --------------------------------------------------- #
    def _toggle_weights(self):
        self.weights_open = not self.weights_open
        if self.weights_open:
            self.weights_frame.grid()
            self.weights_toggle.config(text="▾  Scoring weights")
        else:
            self.weights_frame.grid_remove()
            self.weights_toggle.config(text="▸  Scoring weights")
        self.app.fit_window(self.app.CALC_MIN_WIDTH, keep_position=True)

    def _refresh_weight_note(self, *_):
        """Show what the current weights mean as percentages."""
        try:
            vals = {k: float(v.get()) for k, v in self.weight_vars.items()}
        except ValueError:
            self.weight_note.config(text="")
            return
        total = sum(vals.values())
        if total <= 0:
            text = "All weights are 0, so every factor counts equally."
        else:
            text = "  ·  ".join(f"{METRICS[k][0]} {100 * vals[k] / total:.0f}%"
                             for k in self.keys if vals[k] > 0)
        self.weight_note.config(text=text)

    def _on_cartridge(self):
        """A cartridge was chosen: reveal and fill the load dropdown."""
        items = self.groups[self.cart_var.get()]
        self.label_to_load = {x.label: x for x in items}
        self.grain_combo.config(values=[x.label for x in items])
        chosen = next((x for x in items if x.is_default), items[0])
        self.grain_var.set(chosen.label)
        self.grain_frame.grid()
        self._on_grain()

    def _on_grain(self):
        item = self._selected_load()
        if item:
            self.cost_var.set(f"{item.default_cost:.2f}")
            if item.source == "custom":
                self.remove_link.grid()
            else:
                self.remove_link.grid_remove()

    def _selected_load(self):
        return self.label_to_load.get(self.grain_var.get())

    def _read_number(self, var, name, minimum, maximum=None):
        try:
            value = float(var.get().strip().replace("$", ""))
        except ValueError:
            raise ValueError(f"{name} must be a number.")
        if value < minimum or (maximum is not None and value > maximum):
            if maximum is None:
                raise ValueError(f"{name} must be {minimum:g} or more.")
            raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
        return value

    def _read_inputs(self, need_cost=True):
        dist = self._read_number(self.dist_var, "Distance", 0, self.cat.max_distance)
        gun = self._read_number(self.gun_var, "Gun weight", 0.5, 30)
        cost = self._read_number(self.cost_var, "Cost per round", 0) if need_cost else None
        weights = {k: self._read_number(v, f"{METRICS[k][0]} weight", 0, 10)
                   for k, v in self.weight_vars.items()}
        return dist, gun, cost, weights

    def _payload_text(self, grains):
        if self.cat.show_oz:
            return f"{grains:.0f} gr  ({grains / GRAINS_PER_OZ:.2f} oz)"
        return f"{grains:g} gr"

    def _draw_bar(self):
        self.bar.delete("all")
        if self._last_overall is None:
            return
        score, grade = self._last_overall
        w = max(self.bar.winfo_width(), 60)
        y, r = 11, 6
        self.bar.create_line(r, y, w - r, y, width=r * 2, capstyle="round", fill=SURFACE_2)
        fill_w = (w - 2 * r) * max(0.0, min(100.0, score)) / 100.0
        self.bar.create_line(r, y, r + fill_w, y, width=r * 2, capstyle="round",
                             fill=GRADE_COLORS[grade][0])

    # ---- actions --------------------------------------------------------- #
    def calculate(self, quiet=False):
        item = self._selected_load()
        if item is None:
            if not quiet:
                messagebox.showinfo("Pick a cartridge", "Choose a cartridge and load first.")
            return
        try:
            dist, gun, cost, weights = self._read_inputs()
        except ValueError as exc:
            if not quiet:
                messagebox.showerror("Check your input", str(exc))
            return

        stats = compute_stats(item, dist, gun, cost)
        refs = reference_levels(self.loads, dist, gun)
        scores, overall = score_stats(stats, refs, weights)
        grades = {k: grade_for(s) for k, s in scores.items()}
        overall_grade = grade_for(overall)

        self.res_title.config(text=f"{item.cartridge}  ·  {item.label}")
        self.res_sub.config(text=f"Velocity and energy at {dist:g} yards")
        self.res_values["weight"].config(text=self._payload_text(stats["weight"]))
        self.res_values["velocity"].config(text=f"{stats['velocity']:.0f} fps")
        self.res_values["energy"].config(text=f"{stats['energy']:.0f} ft-lbs")
        self.res_values["recoil"].config(text=f"{stats['recoil']:.1f} ft-lbs")
        self.res_values["cost"].config(text=f"${stats['cost']:.2f}")
        if self.cat.terminal:
            self.res_values["taylor"].config(text=f"{stats['taylor']:.1f}")
        for key, badge in self.res_badges.items():
            bg, fg = GRADE_COLORS[grades[key]]
            badge.config(text=grades[key], bg=bg, fg=fg)
        self.res_overall.config(text=f"{overall_grade}  ·  {overall:.1f}%")

        r_c, n_c, r_a, n_a = rank_among(item, overall, self.loads, dist, gun, weights, refs)
        self.res_rank.config(
            text=f"Ranks #{r_c} of {n_c} {item.cartridge} loads  ·  #{r_a} of {n_a} in "
                 f"{self.cat.title}")
        src = SOURCE_NOTES.get(item.source, DEFAULT_SOURCE_NOTE)
        self.res_note.config(
            text=f"{src} Recoil assumes a {gun:g} lb gun.")
        self.result.grid()
        self._last_overall = (overall, overall_grade)
        self.app.fit_window(self.app.CALC_MIN_WIDTH, keep_position=True)
        self._draw_bar()

    def reset(self):
        self.cart_var.set("")
        self.grain_var.set("")
        self.label_to_load = {}
        self.grain_frame.grid_remove()
        self.cost_var.set("")
        self.dist_var.set(f"{self.cat.default_distance:g}")
        self.gun_var.set(f"{self.cat.default_gun_lb:g}")
        for k, v in self.weight_vars.items():
            v.set(str(default_weights(self.cat)[k]))
        if self.weights_open:
            self._toggle_weights()
        self.result.grid_remove()
        self._last_overall = None
        self.app.fit_window(self.app.CALC_MIN_WIDTH, keep_position=True)

    # ---- user-added calibers --------------------------------------------- #
    def _open_add_dialog(self):
        a, cat = self.app, self.cat
        win = tk.Toplevel(self.root)
        win.configure(bg=BG)
        win.title(f"Add your own caliber — {cat.title}")
        win.transient(self.root)
        win.resizable(False, False)

        body = tk.Frame(win, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        body.pack(padx=18, pady=18, fill="both")
        body.columnconfigure((0, 1, 2), weight=1, uniform="c")
        p = dict(padx=18)

        name_var, wt_var, fps_var, cost_var = (tk.StringVar() for _ in range(4))
        load_var, bc_var, powder_var, dia_var = (tk.StringVar() for _ in range(4))

        a.label(body, "CARTRIDGE NAME", 9, MUTED, True).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(16, 4), **p)
        name_box = ttk.Combobox(body, textvariable=name_var, values=self.cartridges, font=a.f(12))
        name_box.grid(row=1, column=0, columnspan=3, sticky="ew", **p)
        a.label(body, "Pick an existing one to add another load to it, or type a new name.",
                9, MUTED).grid(row=2, column=0, columnspan=3, sticky="w", padx=18, pady=(3, 0))

        for i, (text, var) in enumerate((("BULLET WEIGHT (GR)", wt_var),
                                         ("MUZZLE VELOCITY (FPS)", fps_var),
                                         ("PRICE PER ROUND ($)", cost_var))):
            a.label(body, text, 9, MUTED, True).grid(
                row=3, column=i, sticky="w", pady=(14, 4), padx=(18 if i == 0 else 6, 6 if i < 2 else 18))
            ttk.Entry(body, textvariable=var, font=a.f(12), width=10).grid(
                row=4, column=i, sticky="ew", padx=(18 if i == 0 else 6, 6 if i < 2 else 18))

        more = tk.Frame(body, bg=SURFACE)
        more.columnconfigure((0, 1, 2), weight=1, uniform="m")
        for i, (text, var) in enumerate((("LOAD NAME", load_var), ("BALLISTIC COEFF. (G1)", bc_var),
                                         ("POWDER CHARGE (GR)", powder_var))):
            a.label(more, text, 9, MUTED, True).grid(row=0, column=i, sticky="w", pady=(0, 4),
                                                     padx=(0 if i == 0 else 6, 6 if i < 2 else 0))
            ttk.Entry(more, textvariable=var, font=a.f(12), width=10).grid(
                row=1, column=i, sticky="ew", padx=(0 if i == 0 else 6, 6 if i < 2 else 0))
        a.label(more, "BULLET DIAMETER (IN)", 9, MUTED, True).grid(row=3, column=0, sticky="w", pady=(10, 4))
        ttk.Entry(more, textvariable=dia_var, font=a.f(12), width=10).grid(
            row=4, column=0, sticky="ew", padx=(0, 6))
        a.label(more, f"Leave blank to use typical values (BC {cat.default_bc:g}; powder "
                      f"estimated from the speed and weight). Filling these in makes the recoil "
                      f"and long-range numbers more accurate.",
                9, MUTED, anchor="w", justify="left", wraplength=470).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        state = {"open": False}
        toggle = tk.Label(body, text="▸  More details (optional)", bg=SURFACE, fg=MUTED,
                          font=a.f(10, True), cursor="hand2")
        toggle.grid(row=5, column=0, columnspan=3, sticky="w", pady=(14, 0), **p)

        def flip(_e=None):
            state["open"] = not state["open"]
            if state["open"]:
                more.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0), **p)
                toggle.config(text="▾  More details (optional)")
            else:
                more.grid_remove()
                toggle.config(text="▸  More details (optional)")

        toggle.bind("<Button-1>", flip)

        def parse():
            def num(var, label, lo, hi=None, blank_ok=False):
                text = var.get().strip().replace("$", "")
                if not text:
                    if blank_ok:
                        return None
                    raise ValueError(f"{label} is required.")
                try:
                    v = float(text)
                except ValueError:
                    raise ValueError(f"{label} must be a number.")
                if v < lo or (hi is not None and v > hi):
                    rng = f"between {lo:g} and {hi:g}" if hi is not None else f"{lo:g} or more"
                    raise ValueError(f"{label} must be {rng}.")
                return v

            cart = name_var.get().strip()
            if not cart:
                raise ValueError("Enter a cartridge name.")
            if any(ch in cart for ch in "\n\r"):
                raise ValueError("The cartridge name must be on one line.")
            gr = num(wt_var, "Bullet weight", 1, 2000)
            fps = num(fps_var, "Muzzle velocity", 100, 5500)
            cost = num(cost_var, "Price per round", 0)
            bc = num(bc_var, "Ballistic coefficient", 0.01, 1.5, True)
            powder = num(powder_var, "Powder charge", 0.1, 300, True)
            dia = num(dia_var, "Bullet diameter", 0.1, 0.7, True)
            return dict(category=cat.title, cartridge=cart,
                        load=load_var.get().strip() or "Custom",
                        bullet_gr=f"{gr:g}", muzzle_fps=f"{fps:g}",
                        bc_g1=f"{(bc if bc is not None else cat.default_bc):g}",
                        powder_gr=f"{(powder if powder is not None else estimate_powder(gr, fps)):.1f}",
                        default_cost=f"{cost:.2f}",
                        diameter_in=f"{dia:g}" if dia is not None else "")

        def save(_e=None):
            try:
                row = parse()
                item = load_from_custom_row(row, cat.grain_style)
            except ValueError as exc:
                messagebox.showerror("Check your input", str(exc), parent=win)
                return
            taken = {x.label for x in self.loads if x.cartridge == item.cartridge}
            base, n = item.label, 1
            while item.label in taken:                      # keep dropdown entries unique
                n += 1
                item.label = f"{base} (custom{'' if n == 2 else ' ' + str(n - 1)})"
            try:
                rows = read_custom_rows()
                rows.append(row)
                write_custom_rows(rows)
            except OSError as exc:
                messagebox.showerror("Couldn't save", f"Could not write {CUSTOM_FILENAME}:\n{exc}",
                                     parent=win)
                return
            self.loads.append(item)
            self._regroup()
            self.cart_combo.config(values=self.cartridges)
            self.cart_var.set(item.cartridge)
            self._on_cartridge()
            self.grain_var.set(item.label)
            self._on_grain()
            win.destroy()
            self.app.fit_window(self.app.CALC_MIN_WIDTH, keep_position=True)

        btns = tk.Frame(body, bg=SURFACE)
        btns.grid(row=7, column=0, columnspan=3, sticky="w", pady=(16, 18), **p)
        a.button(btns, "Save caliber", save, "primary").pack(side="left")
        a.button(btns, "Cancel", win.destroy).pack(side="left", padx=8)
        win.bind("<Return>", save)
        win.bind("<Escape>", lambda e: win.destroy())
        name_box.focus_set()

    def _remove_custom(self):
        item = self._selected_load()
        if item is None or item.source != "custom":
            return
        if not messagebox.askyesno("Remove custom load",
                                   f"Remove {item.cartridge} {item.label.strip()} from your list?"):
            return
        try:
            rows = [r for r in read_custom_rows()
                    if not (r.get("category") == self.cat.title and same_custom_row(r, item))]
            write_custom_rows(rows)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Couldn't remove", f"Could not update {CUSTOM_FILENAME}:\n{exc}")
            return
        self.loads.remove(item)
        self._regroup()
        self.cart_combo.config(values=self.cartridges)
        if item.cartridge in self.groups:
            self._on_cartridge()
        else:
            self.reset()

    # ---- compare ---------------------------------------------------------- #
    def compare_all(self):
        a, cat = self.app, self.cat
        try:
            dist, gun, _, weights = self._read_inputs(need_cost=False)
        except ValueError as exc:
            messagebox.showerror("Check your input", str(exc))
            return
        refs = reference_levels(self.loads, dist, gun)
        scored = []
        for item in self.loads:
            stats = compute_stats(item, dist, gun)
            _, overall = score_stats(stats, refs, weights)
            scored.append((item, stats, overall))
        order = sorted(scored, key=lambda t: -t[2])
        rank_of = {id(t[0]): n for n, t in enumerate(order, start=1)}
        rows = [dict(rank=rank_of[id(item)], item=item, stats=stats, score=overall,
                     grade=grade_for(overall)) for item, stats, overall in scored]

        # (heading, width, value getter, sort key, best-first?)
        spec = [("Rank", 52, lambda r: r["rank"], lambda r: r["rank"], False),
                (cat.cartridge_label.title(), 150, lambda r: r["item"].cartridge,
                 lambda r: r["item"].cartridge, False),
                ("Load", 300 if not cat.grain_style else 270, lambda r: r["item"].label,
                 lambda r: r["item"].label.lower(), False),
                (cat.payload_col, 80, lambda r: f"{r['stats']['weight']:.0f}",
                 lambda r: r["stats"]["weight"], True),
                ("Velocity (fps)", 104, lambda r: f"{r['stats']['velocity']:.0f}",
                 lambda r: r["stats"]["velocity"], True),
                ("Energy (ft-lbs)", 112, lambda r: f"{r['stats']['energy']:.0f}",
                 lambda r: r["stats"]["energy"], True),
                ("Recoil (ft-lbs)", 112, lambda r: f"{r['stats']['recoil']:.1f}",
                 lambda r: r["stats"]["recoil"], False)]
        if cat.terminal:
            spec += [("Taylor KO", 84, lambda r: f"{r['stats']['taylor']:.1f}",
                      lambda r: r["stats"]["taylor"], True)]
        spec += [("Cost ($)", 70, lambda r: f"{r['stats']['cost']:.2f}",
                  lambda r: r["stats"]["cost"], False),
                 ("Score (%)", 80, lambda r: f"{r['score']:.1f}", lambda r: r["score"], True),
                 ("Grade", 60, lambda r: r["grade"], lambda r: r["score"], True)]
        cols = [c[0] for c in spec]
        by_col = {c[0]: c for c in spec}

        win = tk.Toplevel(self.root)
        win.configure(bg=BG)
        win.title(f"{cat.title}: all loads at {dist:g} yards")
        # ---- filter bar
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(bar, text="FILTER", bg=BG, fg=MUTED, font=a.f(9, True)).pack(side="left")
        filter_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=filter_var, width=28, font=a.f(11))
        entry.pack(side="left", padx=(8, 12))
        cart_var = tk.StringVar(value="All")
        ttk.Combobox(bar, textvariable=cart_var, values=["All"] + self.cartridges,
                     state="readonly", width=22, font=a.f(11)).pack(side="left")
        count_lbl = tk.Label(bar, text="", bg=BG, fg=MUTED, font=a.f(10))
        count_lbl.pack(side="right")

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=14, pady=(10, 6))
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=min(len(rows), 20))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        for c in spec:
            tree.column(c[0], anchor="w" if c[0] in cols[1:3] else "center")
        a.fit_columns(tree, cols, [[c[2](r) for c in spec] for r in rows], "Load")
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        sort_state = {"col": "Score (%)", "desc": True}
        shown = {}

        def visible():
            terms = filter_var.get().lower().split()
            want = cart_var.get()
            out = []
            for r in rows:
                hay = f"{r['item'].cartridge} {r['item'].label}".lower()
                if want != "All" and r["item"].cartridge != want:
                    continue
                if all(t in hay for t in terms):
                    out.append(r)
            return out

        def render():
            data = visible()
            c = by_col[sort_state["col"]]
            data.sort(key=c[3], reverse=sort_state["desc"] and c[0] != "Rank")
            tree.delete(*tree.get_children())
            shown.clear()
            for r in data:
                iid = tree.insert("", "end", values=[c[2](r) for c in spec])
                shown[iid] = r["item"]
            count_lbl.config(text=f"Showing {len(data)} of {len(rows)} loads")

        def sort_by(col):
            if sort_state["col"] == col:
                desc = not sort_state["desc"]
            else:                                  # first click: best-first for each column
                desc = by_col[col][4]
            sort_state.update(col=col, desc=desc)
            render()

        def jump(_e=None):
            sel = tree.selection()
            if not sel:
                return
            item = shown.get(sel[0])
            win.destroy()
            if item is not None:
                self.show_load(item)

        for col in cols:
            tree.heading(col, text=col, command=lambda c=col: sort_by(c))
        tree.bind("<Double-1>", jump)
        tree.bind("<Return>", jump)
        filter_var.trace_add("write", lambda *_: render())
        cart_var.trace_add("write", lambda *_: render())
        tk.Label(win, text="Type to filter (e.g. \"federal 168\"). Click a heading to sort. "
                           "Double-click a row to open it in the calculator. Scores use your "
                           "current weights and each load's default price.",
                 bg=BG, fg=MUTED, font=a.f(9)).pack(pady=(0, 12))
        render()
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        if win.winfo_reqwidth() > sw - 40 or win.winfo_reqheight() > sh - 90:
            # keep it on small screens; the Load column gives up width first
            w, h = min(win.winfo_reqwidth(), sw - 40), min(win.winfo_reqheight(), sh - 90)
            win.geometry(f"{w}x{h}+{(sw - w) // 2}+20")
        entry.focus_set()

    def show_load(self, item):
        """Select a load in the main form (used by Compare All)."""
        self.cart_var.set(item.cartridge)
        self._on_cartridge()
        self.grain_var.set(item.label)
        self._on_grain()
        self.calculate(quiet=True)


def open_handload_dialog(app, cat, parent, cartridges, existing=None, duplicate=False, on_saved=None):
    """Add / edit a handload. `existing` is a handload record (dict) to start from."""
    win = tk.Toplevel(parent)
    win.configure(bg=BG)
    verb = "Edit" if existing and not duplicate else "Add"
    win.title(f"{verb} handload — {cat.title}")
    win.transient(parent)
    win.resizable(False, False)
    body = tk.Frame(win, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
    body.pack(padx=16, pady=16, fill="both")
    for c in range(3):
        body.columnconfigure(c, weight=1, uniform="c")
    ex = dict(existing or {})
    V = {k: tk.StringVar(value=str(ex.get(k, ""))) for k in (
        "cartridge", "name", "bullet_maker", "bullet", "bullet_gr", "diameter_in", "bc_g1",
        "powder", "powder_gr", "muzzle_fps", "barrel_in", "purpose", "bullet_cost",
        "powder_cost_lb", "primer_cost", "brass_cost", "brass_reuse", "total", "notes")}
    if not ex.get("brass_reuse"):
        V["brass_reuse"].set("5")
    if ex and not ex.get("bullet_cost") and ex.get("cost"):
        V["total"].set(ex["cost"])
    if duplicate and V["name"].get():
        V["name"].set(V["name"].get() + " (copy)")
    OTHER = "Other / custom"
    bullets = app.bullets

    def lab(text, row, col, span=1, pady=(10, 3)):
        app.label(body, text, 9, MUTED, True).grid(
            row=row, column=col, columnspan=span, sticky="w", pady=pady,
            padx=(18 if col == 0 else 6, 6 if col + span < 3 else 18))

    def ent(var, row, col, span=1, kind="entry", values=(), state=None):
        px = dict(padx=(18 if col == 0 else 6, 6 if col + span < 3 else 18))
        if kind == "combo":
            w = ttk.Combobox(body, textvariable=var, values=list(values), font=app.f(11),
                             state=state or "normal")
        else:
            w = ttk.Entry(body, textvariable=var, font=app.f(11))
        w.grid(row=row, column=col, columnspan=span, sticky="ew", **px)
        return w

    def section(text, row):
        tk.Frame(body, bg=BORDER, height=1).grid(row=row, column=0, columnspan=3, sticky="ew",
                                                 padx=18, pady=(16, 0))
        app.label(body, text, 9, ACCENT, True).grid(row=row + 1, column=0, columnspan=3,
                                                    sticky="w", padx=18, pady=(8, 0))

    lab("CARTRIDGE", 0, 0, 2, (16, 3))
    lab("PURPOSE", 0, 2, 1, (16, 3))
    cart_box = ent(V["cartridge"], 1, 0, 2, "combo", cartridges)
    ent(V["purpose"], 1, 2, 1, "combo", PURPOSES, "readonly")
    lab("LOAD NAME (OPTIONAL)", 2, 0, 3)
    ent(V["name"], 3, 0, 3)

    section("BULLET", 4)
    lab("MAKER", 6, 0, 1, (6, 3))
    lab("BULLET", 6, 1, 2, (6, 3))
    makers = sorted({b["maker"] for b in bullets}) + [OTHER]
    maker_box = ent(V["bullet_maker"], 7, 0, 1, "combo", makers, "readonly")
    bullet_box = ent(V["bullet"], 7, 1, 2, "combo", [], "readonly")
    lab("WEIGHT (GR)", 8, 0)
    lab("DIAMETER (IN)", 8, 1)
    lab("BC (G1)", 8, 2)
    ent(V["bullet_gr"], 9, 0)
    ent(V["diameter_in"], 9, 1)
    ent(V["bc_g1"], 9, 2)
    note = app.label(body, "Pick a bullet to fill these in, or just type your own. Leave diameter / "
                           "BC blank to estimate them.", 9, MUTED, anchor="w")
    note.grid(row=10, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 0))

    section("POWDER AND PERFORMANCE", 11)
    lab("POWDER", 13, 0, 1, (6, 3))
    lab("CHARGE (GR)", 13, 1, 1, (6, 3))
    lab("MUZZLE VELOCITY (FPS)", 13, 2, 1, (6, 3))
    ent(V["powder"], 14, 0, 1, "combo", POWDERS)
    ent(V["powder_gr"], 14, 1)
    ent(V["muzzle_fps"], 14, 2)
    lab("BARREL LENGTH (IN, OPTIONAL)", 15, 0, 2)
    ent(V["barrel_in"], 16, 0)

    section("COST PER ROUND", 17)
    for i, (t, k) in enumerate((("BULLET ($ EACH)", "bullet_cost"), ("POWDER ($ PER LB)", "powder_cost_lb"),
                                ("PRIMER ($ EACH)", "primer_cost"))):
        lab(t, 19, i, 1, (6, 3))
        ent(V[k], 20, i)
    for i, (t, k) in enumerate((("BRASS ($ EACH)", "brass_cost"), ("BRASS RELOADS", "brass_reuse"),
                                ("OR TOTAL PER ROUND ($)", "total"))):
        lab(t, 21, i)
        ent(V[k], 22, i)
    cost_lbl = app.label(body, "", 11, TEXT, True, anchor="w")
    cost_lbl.grid(row=23, column=0, columnspan=3, sticky="w", padx=18, pady=(8, 0))
    lab("NOTES (OPTIONAL)", 24, 0, 3)
    ent(V["notes"], 25, 0, 3)
    app.label(body, "Handload figures are only as good as your data. Always follow published load "
                    "manuals; this app doesn't check pressure or safety.", 9, MUTED, anchor="w",
              justify="left", wraplength=560).grid(row=26, column=0, columnspan=3, sticky="w",
                                                   padx=18, pady=(10, 0))

    def num(key, label, lo, hi=None, blank=False):
        text = V[key].get().strip().replace("$", "")
        if not text:
            if blank:
                return None
            raise ValueError(f"{label} is required.")
        try:
            v = float(text)
        except ValueError:
            raise ValueError(f"{label} must be a number.")
        if v < lo or (hi is not None and v > hi):
            raise ValueError(f"{label} must be " + (f"between {lo:g} and {hi:g}." if hi is not None
                                                    else f"{lo:g} or more."))
        return v

    def parts_cost():
        try:
            get = lambda k, d=0.0: float(V[k].get().strip().replace("$", "") or d)
            return handload_cost(get("bullet_cost"), get("powder_cost_lb"), get("powder_gr"),
                                 get("primer_cost"), get("brass_cost"), get("brass_reuse", 5))
        except ValueError:
            return None

    def update_cost(*_):
        total = V["total"].get().strip().replace("$", "")
        try:
            c = float(total) if total else parts_cost()
        except ValueError:
            c = None
        cost_lbl.config(text="" if not c else f"Cost per round: ${c:.2f}")

    def refresh_bullets(*_):
        d = DIAMETERS.get(V["cartridge"].get().strip())
        maker = V["bullet_maker"].get()
        names = []
        for b in bullets:
            if maker and maker != OTHER and b["maker"] != maker:
                continue
            if d and abs(b["diameter"] - d) > 0.003:
                continue
            names.append(f"{b['name']} · {b['weight']:g} gr")
        bullet_box.config(values=names, state="readonly" if maker and maker != OTHER else "disabled")

    def pick_bullet(*_):
        maker, label = V["bullet_maker"].get(), V["bullet"].get()
        d = DIAMETERS.get(V["cartridge"].get().strip())
        for b in bullets:
            if b["maker"] == maker and f"{b['name']} · {b['weight']:g} gr" == label and (
                    not d or abs(b["diameter"] - d) <= 0.003):
                V["bullet_gr"].set(f"{b['weight']:g}")
                V["diameter_in"].set(f"{b['diameter']:g}")
                V["bc_g1"].set(f"{b['bc']:g}")
                V["bullet"].set(label)
                break

    maker_box.bind("<<ComboboxSelected>>", lambda e: (V["bullet"].set(""), refresh_bullets()))
    bullet_box.bind("<<ComboboxSelected>>", pick_bullet)
    cart_box.bind("<<ComboboxSelected>>", refresh_bullets)
    V["cartridge"].trace_add("write", refresh_bullets)
    for k in ("bullet_cost", "powder_cost_lb", "powder_gr", "primer_cost", "brass_cost",
              "brass_reuse", "total"):
        V[k].trace_add("write", update_cost)
    refresh_bullets()
    update_cost()

    def save(_e=None):
        try:
            cart = V["cartridge"].get().strip()
            if not cart:
                raise ValueError("Enter a cartridge.")
            gr = num("bullet_gr", "Bullet weight", 1, 2000)
            fps = num("muzzle_fps", "Muzzle velocity", 100, 5500)
            charge = num("powder_gr", "Powder charge", 0.1, 300)
            dia = num("diameter_in", "Bullet diameter", 0.1, 0.7, True)
            bc = num("bc_g1", "Ballistic coefficient", 0.01, 1.5, True)
            barrel = num("barrel_in", "Barrel length", 1, 60, True)
            if dia is None:
                dia = DIAMETERS.get(cart) or bullet_diameter(cart, gr)
            if bc is None:
                bc = estimate_bc(gr, dia, cat.title == "Handgun")
            total = V["total"].get().strip().replace("$", "")
            cost = float(total) if total else parts_cost()
            if total:
                num("total", "Total cost", 0)
            if not cost or cost <= 0:
                raise ValueError("Enter what a round costs (the parts, or a total per round).")
        except ValueError as exc:
            messagebox.showerror("Check your input", str(exc), parent=win)
            return
        row = dict(id=ex.get("id") if existing and not duplicate else new_handload_id(),
                   category=cat.title, cartridge=cart, name=V["name"].get().strip(),
                   bullet_maker=V["bullet_maker"].get() if V["bullet_maker"].get() != OTHER else "",
                   bullet=V["bullet"].get().split(" · ")[0] if V["bullet"].get() else "",
                   bullet_gr=f"{gr:g}", diameter_in=f"{dia:g}", bc_g1=f"{bc:g}",
                   powder=V["powder"].get().strip(), powder_gr=f"{charge:g}", muzzle_fps=f"{fps:g}",
                   barrel_in=f"{barrel:g}" if barrel else "", purpose=V["purpose"].get(),
                   cost=f"{cost:.4f}", bullet_cost=V["bullet_cost"].get().strip(),
                   powder_cost_lb=V["powder_cost_lb"].get().strip(),
                   primer_cost=V["primer_cost"].get().strip(), brass_cost=V["brass_cost"].get().strip(),
                   brass_reuse=V["brass_reuse"].get().strip(), notes=V["notes"].get().strip())
        try:
            app.save_handload(row)
        except OSError as exc:
            messagebox.showerror("Couldn't save", f"Could not write {HANDLOAD_FILENAME}:\n{exc}",
                                 parent=win)
            return
        win.destroy()
        if on_saved:
            on_saved(row)

    btns = tk.Frame(body, bg=SURFACE)
    btns.grid(row=27, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 18))
    app.button(btns, "Save handload", save, "primary").pack(side="left")
    app.button(btns, "Cancel", win.destroy).pack(side="left", padx=8)
    win.bind("<Escape>", lambda e: win.destroy())
    try:
        win.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - win.winfo_height()) // 3)
        win.geometry(f"+{x}+{y}")
        win.grab_set()
    except tk.TclError:
        pass
    cart_box.focus_set()
    return win


class LoadsView:
    """'Compare Loads' tab: every brand's load of ONE cartridge, graded against each other."""
    tab = "loads"

    def __init__(self, app, stage, cat, loads, error=""):
        self.app, self.root, self.cat = app, app.root, cat
        self.loads = loads
        self.groups = group_by_cartridge(loads, True)
        self.cartridges = list(self.groups)
        self.cart_var = tk.StringVar(value="")
        self.dist_var = tk.StringVar(value=f"{cat.default_distance:g}")
        self.gun_var = tk.StringVar(value=f"{cat.default_gun_lb:g}")
        self.filter_var = tk.StringVar(value="")
        self.price_var = tk.StringVar(value="")
        self.keys = metric_keys(cat)
        self.purpose = "All"              # active purpose chip (All / Hunting / Target / ...)
        self.source = "All"               # All / Factory / Handloads
        self.chips = {}
        self.src_chips = {}
        self.weight_vars = {k: tk.StringVar(value=str(v)) for k, v in default_weights(cat).items()}
        self.weights_open = False
        self.rows = []                    # computed rows for the chosen cartridge
        self.iid_row = {}
        self.selected = None              # the Load currently shown in the detail card
        self.sort = {"col": "#", "desc": False}
        self._pending = None
        self._build_ui(stage, error)
        if hasattr(self, "tree"):
            for var in (self.dist_var, self.gun_var, self.filter_var, *self.weight_vars.values()):
                var.trace_add("write", self._schedule)
            self.weight_vars_note()
            if self.cartridges:                       # start on the cartridge with the most loads
                self.cart_var.set(max(self.cartridges, key=lambda c: len(self.groups[c])))
                self._on_cartridge()

    # ---- layout ---------------------------------------------------------- #
    def _build_ui(self, stage, error):
        a, cat = self.app, self.cat
        outer = tk.Frame(stage, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        outer.columnconfigure(0, weight=1)
        a.header(outer, cat, "loads").grid(row=0, column=0, sticky="ew", pady=(0, 16))
        if error or not self.loads:
            msg = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
            msg.grid(row=3, column=0, sticky="ew")
            a.label(msg, error or "No loads found.", 11, TEXT, True, anchor="w").pack(
                anchor="w", padx=18, pady=(16, 4))
            a.label(msg, f"Put {cat.loads_filename} next to the program to use this tab.",
                    10, MUTED, anchor="w").pack(anchor="w", padx=18, pady=(0, 16))
            return

        card = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=3, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        pad = dict(padx=18)
        top = tk.Frame(card, bg=SURFACE)
        top.grid(row=0, column=0, sticky="ew", pady=(16, 0), **pad)
        top.columnconfigure(0, weight=3, minsize=a.px(300))
        for i in (1, 2, 3):
            top.columnconfigure(i, weight=1)
        fields = ((cat.cartridge_label, None), ("DISTANCE (YD)", self.dist_var),
                  (cat.gun_label, self.gun_var), ("FILTER BRAND / LOAD", self.filter_var))
        for i, (text, var) in enumerate(fields):
            a.label(top, text, 9, MUTED, True).grid(row=0, column=i, sticky="w",
                                                     padx=(0 if i == 0 else 8, 0))
            if var is None:
                self.cart_combo = ttk.Combobox(top, textvariable=self.cart_var,
                                               values=self.cartridges, state="readonly",
                                               font=a.f(12),
                                               width=max([16] + [len(c) for c in self.cartridges]))
                self.cart_combo.grid(row=1, column=i, sticky="ew", pady=(4, 0))
                self.cart_combo.bind("<<ComboboxSelected>>", lambda e: self._on_cartridge())
            else:
                ttk.Entry(top, textvariable=var, font=a.f(12), width=10).grid(
                    row=1, column=i, sticky="ew", pady=(4, 0), padx=(8, 0))
        self.chip_row = tk.Frame(card, bg=SURFACE)
        self.chip_row.grid(row=5, column=0, sticky="w", pady=(12, 0), **pad)
        self.src_row = tk.Frame(card, bg=SURFACE)
        self.src_row.grid(row=6, column=0, sticky="w", pady=(8, 16), **pad)
        self.status = a.label(card, "", 10, "#e5534b", anchor="w")
        self.status.grid(row=1, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_toggle = tk.Label(card, text="▸  Scoring weights", bg=SURFACE, fg=MUTED,
                                       font=a.f(10, True), cursor="hand2")
        self.weights_toggle.grid(row=2, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_toggle.bind("<Button-1>", lambda e: self._toggle_weights())
        if cat.grain_style:
            add = tk.Label(card, text="+  Add handload", bg=SURFACE, fg=ACCENT, font=a.f(10, True),
                           cursor="hand2")
            add.grid(row=2, column=0, sticky="e", pady=(8, 0), **pad)
            add.bind("<Button-1>", lambda e: self._open_handload())
        self.weights_frame = tk.Frame(card, bg=SURFACE)
        for i, key in enumerate(self.keys):
            a.label(self.weights_frame, METRICS[key][0], 10, MUTED).grid(
                row=0, column=i * 2, padx=(0 if i == 0 else 14, 6))
            ttk.Spinbox(self.weights_frame, from_=0, to=10, increment=1, width=3,
                        textvariable=self.weight_vars[key], font=a.f(11)).grid(
                row=0, column=i * 2 + 1)
        self.weight_note = a.label(self.weights_frame, "", 9, TEXT, True)
        self.weight_note.grid(row=1, column=0, columnspan=12, sticky="w", pady=(8, 0))
        self.weights_frame.grid(row=3, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_frame.grid_remove()
        a.label(card, "", 4).grid(row=4, column=0)

        # ---- ranked table
        tbl = tk.Frame(outer, bg=BG)
        tbl.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        tbl.columnconfigure(0, weight=1)
        self.count_lbl = a.label(tbl, "Choose a cartridge to see how every brand's load compares.",
                                 10, MUTED, bg=BG, anchor="w")
        self.count_lbl.grid(row=0, column=0, sticky="w", pady=(0, 6))
        # (for bullets the weight is already in the Load text, so no separate Grains column)
        self.cols = ["#", "Load"] + ([] if cat.grain_style else [cat.payload_col])
        if cat.grain_style:
            self.cols += ["Barrel", "Use"]
        self.cols += ["Velocity", "Energy", "Recoil"]
        if cat.terminal:
            self.cols += ["Taylor"]
        self.cols += ["Price", "Score", "Grade"]
        frame = tk.Frame(tbl, bg=BG)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=self.cols, show="headings", height=12,
                                 selectmode="browse")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        for col in self.cols:
            # widths are measured from the text in _render; the Load column takes spare room
            self.tree.column(col, anchor="w" if col in ("Load", "Use") else "center")
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
        self.col_widths, self.sized = {}, False
        hscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)

        def xset(first, last):
            # only show the horizontal scrollbar when the table really is wider than the window
            if float(first) <= 0.0 and float(last) >= 1.0:
                hscroll.grid_remove()
            else:
                hscroll.grid()
            hscroll.set(first, last)
        self.tree.configure(xscrollcommand=xset)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        hscroll.grid_remove()
        self.tree.tag_configure("hand", foreground="#5fd1b4")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        # ---- selected load
        self.detail = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.detail.columnconfigure(0, weight=1)
        self.d_title = a.label(self.detail, "", 13, TEXT, True, anchor="w", justify="left",
                               wraplength=a.px(820))
        self.d_title.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        self.d_info = a.label(self.detail, "", 10, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_info.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 10))
        # the four factors sit side by side, packed to the left (no stretched columns)
        factors = tk.Frame(self.detail, bg=SURFACE)
        factors.grid(row=2, column=0, sticky="w", padx=18)
        self.d_badges = {}
        for i, key in enumerate(self.keys):
            cell = tk.Frame(factors, bg=SURFACE)
            cell.pack(side="left", padx=(0, 28))
            a.label(cell, METRICS[key][0].upper(), 8, MUTED, True).pack(anchor="w")
            line = tk.Frame(cell, bg=SURFACE)
            line.pack(anchor="w", pady=(2, 0))
            val = a.label(line, "", 11, TEXT, True)
            val.pack(side="left")
            badge = tk.Label(line, text="", width=2, font=a.f(10, True))
            badge.pack(side="left", padx=(6, 0))
            self.d_badges[key] = (val, badge)
        priceline = tk.Frame(self.detail, bg=SURFACE)
        self.priceline = priceline
        priceline.grid(row=3, column=0, sticky="w", padx=18, pady=(14, 0))
        self.handline = tk.Frame(self.detail, bg=SURFACE)
        self.handline.grid(row=3, column=0, sticky="w", padx=18, pady=(14, 0))
        a.button(self.handline, "Edit", lambda: self._open_handload(self.selected)).pack(side="left")
        a.button(self.handline, "Duplicate",
                 lambda: self._open_handload(self.selected, duplicate=True)).pack(side="left", padx=8)
        a.button(self.handline, "Delete", self._delete_handload).pack(side="left")
        self.handline.grid_remove()
        a.label(priceline, "YOUR PRICE PER ROUND ($)", 9, MUTED, True).pack(side="left")
        ttk.Entry(priceline, textvariable=self.price_var, width=8, font=a.f(11)).pack(
            side="left", padx=8)
        a.button(priceline, "Set price", self._set_price, "primary").pack(side="left")
        a.button(priceline, "Use catalog estimate", self._reset_price).pack(side="left", padx=8)
        self.d_note = a.label(self.detail, "", 9, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_note.grid(row=4, column=0, sticky="w", padx=18, pady=(10, 14))
        self.detail.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self.detail.grid_remove()
        a.label(outer, f"Grades compare loads of the same cartridge with each other (the average "
                       f"scores {REL_CENTER:.0f}); they can't be compared with Compare Cartridges "
                       "grades. Prices are estimates: set your own.",
                9, MUTED, bg=BG, anchor="w", justify="left", wraplength=a.px(880)).grid(
            row=6, column=0, sticky="w", pady=(10, 0))

    # ---- state ------------------------------------------------------------ #
    def snapshot(self):
        return dict(cart=self.cart_var.get(), dist=self.dist_var.get(), gun=self.gun_var.get(),
                    weights={k: v.get() for k, v in self.weight_vars.items()},
                    weights_open=self.weights_open, purpose=self.purpose, source=self.source)

    def restore(self, snap):
        if not self.loads or not hasattr(self, "tree"):
            return
        self.purpose = snap.get("purpose", "All")
        self.source = snap.get("source", "All")
        for k, v in snap.get("weights", {}).items():
            if k in self.weight_vars:
                self.weight_vars[k].set(v)
        if "dist" in snap:
            self.dist_var.set(snap["dist"])
        if "gun" in snap:
            self.gun_var.set(snap["gun"])
        if snap.get("weights_open") and not self.weights_open:
            self._toggle_weights()
        if snap.get("cart") in self.groups:
            self.cart_var.set(snap["cart"])
            self._on_cartridge()

    # ---- helpers ---------------------------------------------------------- #
    def _toggle_weights(self):
        self.weights_open = not self.weights_open
        if self.weights_open:
            self.weights_frame.grid()
        else:
            self.weights_frame.grid_remove()
        self.weights_toggle.config(text=("▾" if self.weights_open else "▸") + "  Scoring weights")
        self.app.fit_window(self.app.LOADS_MIN_WIDTH, keep_position=True)

    def weight_vars_note(self, *_):
        try:
            vals = {k: float(v.get()) for k, v in self.weight_vars.items()}
        except ValueError:
            self.weight_note.config(text="")
            return
        total = sum(vals.values())
        self.weight_note.config(
            text="All weights are 0, so every factor counts equally." if total <= 0 else
            "  ·  ".join(f"{METRICS[k][0]} {100 * vals[k] / total:.0f}%"
                      for k in self.keys if vals[k] > 0))

    def _schedule(self, *_):
        """Recompute shortly after typing stops."""
        self.weight_vars_note()
        if self._pending is not None:
            try:
                self.root.after_cancel(self._pending)
            except Exception:
                pass
        self._pending = self.root.after(250, self.refresh)

    @staticmethod
    def _num(var, name, lo, hi=None):
        try:
            v = float(var.get().strip().replace("$", ""))
        except ValueError:
            raise ValueError(f"{name} must be a number.")
        if v < lo or (hi is not None and v > hi):
            raise ValueError(f"{name} must be {lo:g} or more." if hi is None
                             else f"{name} must be between {lo:g} and {hi:g}.")
        return v

    def _on_cartridge(self):
        self.filter_var.set("")
        if self.purpose not in self._purposes_of(self.cart_var.get()):
            self.purpose = "All"
        self._build_chips(self.cart_var.get())
        self.selected = None
        self.detail.grid_remove()
        self.refresh()

    def _reload_loads(self, select=None):
        """After adding / editing / deleting a handload: rebuild the lists and redraw."""
        info = self.app.data[self.cat.title]
        self.loads = info["detail"] + self.app.hand_loads(self.cat)
        self.groups = group_by_cartridge(self.loads, True)
        self.cartridges = list(self.groups)
        self.cart_combo.config(values=self.cartridges,
                               width=max([16] + [len(c) for c in self.cartridges]))
        cart = select.cartridge if select else self.cart_var.get()
        if cart not in self.groups:
            cart = max(self.cartridges, key=lambda c: len(self.groups[c])) if self.cartridges else ""
        self.cart_var.set(cart)
        self.selected = None
        self.detail.grid_remove()
        if self.purpose not in self._purposes_of(cart):
            self.purpose = "All"
        self._build_chips(cart)
        self.refresh()
        if select is not None:
            for it in self.groups.get(cart, []):
                if it.handload and it.hid == select.hid:
                    self.selected = it
                    self._reselect()
                    break

    def _open_handload(self, item=None, duplicate=False):
        carts = [c for c in self.cartridges]
        for b in self.app.data[self.cat.title]["loads"]:
            if b.cartridge not in carts:
                carts.append(b.cartridge)
        existing = dict(item.info) if item is not None and item.handload else None

        def saved(row):
            new = load_from_handload_row(row, self.cat.grain_style)
            self.purpose = "All"
            self.source = "All"
            self._reload_loads(select=new)
        open_handload_dialog(self.app, self.cat, self.root, carts, existing, duplicate, saved)

    def _delete_handload(self):
        item = self.selected
        if item is None or not item.handload:
            return
        if not messagebox.askyesno("Delete handload", f"Delete \"{item.load}\" from your handloads?"):
            return
        try:
            self.app.delete_handload(item.hid)
        except OSError as exc:
            messagebox.showerror("Couldn't delete", f"Could not write {HANDLOAD_FILENAME}:\n{exc}")
            return
        self._reload_loads()

    # ---- purpose chips ---------------------------------------------------- #
    def _purpose_of(self, item):
        return item.purpose or item.group or ""

    def _purposes_of(self, cart):
        counts = {}
        for x in self.groups.get(cart, []):
            p = self._purpose_of(x)
            if p:
                counts[p] = counts.get(p, 0) + 1
        order = ["Hunting", "Varmint", "Target", "Match", "Defense", "Subsonic",
                 "Game", "Waterfowl", "Turkey", "Buckshot", "Slug"]
        names = sorted(counts, key=lambda n: (order.index(n) if n in order else 99, n))
        return ["All"] + names

    def _build_source_chips(self, cart):
        for w in self.src_row.winfo_children():
            w.destroy()
        self.src_chips = {}
        items = self.groups.get(cart, [])
        nh = sum(x.handload for x in items)
        if not nh:
            self.source = "All"
            self.src_row.grid_remove()
            return
        self.src_row.grid()
        self.app.label(self.src_row, "SHOW", 9, MUTED, True).pack(side="left", padx=(0, 10))
        for name, n in (("All", len(items)), ("Factory", len(items) - nh), ("Handloads", nh)):
            chip = tk.Label(self.src_row, text=f"{name} ({n})", font=self.app.f(10, True),
                            padx=10, pady=4, cursor="hand2")
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda e, nm=name: self._pick_source(nm))
            self.src_chips[name] = chip
        self._style_chips()

    def _pick_source(self, name):
        self.source = name
        self.selected = None
        self.detail.grid_remove()
        self._style_chips()
        self._render()

    def _build_chips(self, cart):
        for w in self.chip_row.winfo_children():
            w.destroy()
        self.chips = {}
        self._build_source_chips(cart)
        items = self.groups.get(cart, [])
        names = self._purposes_of(cart)
        if len(names) <= 2:                      # only one purpose: nothing to pick between
            return
        self.app.label(self.chip_row, "PURPOSE", 9, MUTED, True).pack(side="left", padx=(0, 10))
        for name in names:
            n = len(items) if name == "All" else sum(self._purpose_of(x) == name for x in items)
            chip = tk.Label(self.chip_row, text=f"{name} ({n})", font=self.app.f(10, True),
                            padx=10, pady=4, cursor="hand2")
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda e, nm=name: self._pick_purpose(nm))
            self.chips[name] = chip
        self._style_chips()

    def _style_chips(self):
        for name, chip in self.chips.items():
            on = name == self.purpose
            chip.config(bg=ACCENT if on else SURFACE_2, fg="#ffffff" if on else TEXT)
        for name, chip in self.src_chips.items():
            on = name == self.source
            chip.config(bg=ACCENT if on else SURFACE_2, fg="#ffffff" if on else TEXT)

    def _pick_purpose(self, name):
        self.purpose = name
        self.selected = None
        self.detail.grid_remove()
        self._style_chips()
        self.refresh()

    # ---- compute + render ------------------------------------------------- #
    def refresh(self):
        self._pending = None
        alive = getattr(self.tree, "winfo_exists", None)
        if alive is not None and not alive():          # a delayed refresh after leaving this tab
            return
        cart = self.cart_var.get()
        items = self.groups.get(cart)
        if not items:
            return
        if self.purpose != "All":
            items = [x for x in items if self._purpose_of(x) == self.purpose]
        try:
            dist = self._num(self.dist_var, "Distance", 0, self.cat.max_distance)
            gun = self._num(self.gun_var, "Gun weight", 0.5, 30)
            weights = {k: self._num(v, f"{METRICS[k][0]} weight", 0, 10)
                       for k, v in self.weight_vars.items()}
        except ValueError as exc:
            self.status.config(text=str(exc))
            return
        self.status.config(text="")
        stats = [compute_stats(x, dist, gun, self.app.price_for(self.cat, x)) for x in items]
        # shotshells are only comparable with the same type (Target vs Target, Buckshot vs Buckshot)
        keys = [x.group if not self.cat.grain_style else "" for x in items]
        self.group_order = {k: n for n, k in enumerate(dict.fromkeys(keys))}
        scored, rank, peers = [None] * len(items), {}, {}
        for key in self.group_order:
            idx = [i for i, k in enumerate(keys) if k == key]
            for i, res in zip(idx, relative_scores([stats[i] for i in idx], weights)):
                scored[i] = res
            for n, i in enumerate(sorted(idx, key=lambda i: -scored[i][1]), start=1):
                rank[i], peers[i] = n, len(idx)
        self.rows = []
        for i, item in enumerate(items):
            sc, overall = scored[i]
            self.rows.append(dict(item=item, stats=stats[i], scores=sc, overall=overall,
                                  grade=grade_relative(overall), rank=rank[i], peers=peers[i],
                                  group=keys[i],
                                  custom_price=abs(stats[i]["cost"] - item.default_cost) > 1e-9))
        self.dist = dist
        self._render()

    def _sort_by(self, col):
        if self.sort["col"] == col:
            self.sort["desc"] = not self.sort["desc"]
        else:
            self.sort = {"col": col, "desc": col in (self.cat.payload_col, "Velocity", "Energy",
                                                    "Taylor", "Score")}
        if col == "#":
            self.sort["desc"] = False
        self._render()

    def _render(self):
        terms = self.filter_var.get().lower().split()
        data = [r for r in self.rows if all(t in r["item"].label.lower() for t in terms)
                and (self.source == "All" or r["item"].handload == (self.source == "Handloads"))]
        keys = {"#": lambda r: (self.group_order.get(r["group"], 0), r["rank"]), "Load": lambda r: (r["stats"]["weight"], r["item"].label.lower()),
                self.cat.payload_col: lambda r: r["stats"]["weight"],
                "Barrel": lambda r: r["item"].barrel_in or 999,
                "Use": lambda r: (r["item"].purpose, r["rank"]),
                "Velocity": lambda r: r["stats"]["velocity"],
                "Energy": lambda r: r["stats"]["energy"],
                "Recoil": lambda r: r["stats"]["recoil"],
                "Taylor": lambda r: r["stats"]["taylor"],
                "Price": lambda r: r["stats"]["cost"], "Score": lambda r: r["overall"],
                "Grade": lambda r: r["overall"]}
        data.sort(key=keys[self.sort["col"]], reverse=self.sort["desc"])
        self.tree.delete(*self.tree.get_children())
        self.iid_row = {}
        keep = None
        cells = []
        for r in data:
            st = r["stats"]
            it = r["item"]
            vals = [r["rank"], it.label + ("  (handload)" if it.handload else "")]
            if self.cat.grain_style:
                vals += [f"{it.barrel_in:g}\"" if it.barrel_in else "—", it.purpose]
            else:
                vals += [f"{st['weight']:g}"]
            vals += [f"{st['velocity']:.0f}", f"{st['energy']:.0f}", f"{st['recoil']:.1f}"]
            if self.cat.terminal:
                vals += [f"{st['taylor']:.1f}"]
            vals += [f"{st['cost']:.2f}" + (" ✎" if r["custom_price"] else ""),
                     f"{r['overall']:.0f}", r["grade"]]
            cells.append(vals)
            iid = self.tree.insert("", "end", values=vals, tags=("hand",) if it.handload else ())
            self.iid_row[iid] = r
            if self.selected is r["item"]:
                keep = iid
        self.count_lbl.config(
            text=f"{self.cart_var.get()}"
                 f"{'' if self.purpose == 'All' else '  ·  ' + self.purpose}: {len(data)} of "
                 f"{len(self.rows)} loads at {self.dist:g} yards")
        if keep:
            self.tree.selection_set(keep)
            self.tree.see(keep)
        elif self.selected is not None:
            self.selected = None
            self.detail.grid_remove()
        self.app.fit_columns(self.tree, self.cols, cells, "Load", self.col_widths)
        if not self.sized and cells:
            # first time this table is shown: widen the window if every column doesn't fit
            self.sized = True
            self.app.root.update_idletasks()
            self.app.grow_to_fit(sum(self.col_widths.values()) - self.tree.winfo_width())
        self.app.fit_window(self.app.LOADS_MIN_WIDTH, keep_position=True)

    def _on_select(self):
        sel = self.tree.selection()
        row = self.iid_row.get(sel[0]) if sel else None
        if row is None:
            return
        item, st = row["item"], row["stats"]
        self.selected = item
        self.d_title.config(text=f"{item.cartridge}  ·  {item.label}")
        info = [f"{st['weight']:g} {'gr' if self.cat.grain_style else 'gr payload'}"]
        if self.cat.grain_style:
            info.append(f"{item.barrel_in:g} in test barrel" if item.barrel_in
                        else "test barrel length not listed")
        if item.purpose:
            info.append(item.purpose)
        if item.handload and item.info:
            h = item.info
            if h.get("bullet"):
                info.insert(0, f"{h.get('bullet_maker', '')} {h['bullet']}".strip())
            if h.get("powder"):
                info.append(f"{h['powder']} {float(h['powder_gr']):g} gr")
        self.d_info.config(text="  ·  ".join(info))
        vals = {"velocity": f"{st['velocity']:.0f} fps", "energy": f"{st['energy']:.0f} ft-lbs",
                "recoil": f"{st['recoil']:.1f} ft-lbs", "cost": f"${st['cost']:.2f}",
                "taylor": f"{st['taylor']:.1f}"}
        for key, (val, badge) in self.d_badges.items():
            grade = grade_relative(row["scores"][key])
            bg, fg = GRADE_COLORS[grade]
            val.config(text=vals[key])
            badge.config(text=grade, bg=bg, fg=fg)
        self.price_var.set(f"{st['cost']:.2f}")
        if item.handload:
            self.priceline.grid_remove()
            self.handline.grid()
        else:
            self.handline.grid_remove()
            self.priceline.grid()
        src = SOURCE_NOTES.get(item.source, DEFAULT_SOURCE_NOTE)
        if item.handload and item.info and item.info.get("notes"):
            src = item.info["notes"] + "  " + src
        self.d_note.config(text=f"Overall {row['grade']}  ·  {row['overall']:.0f}  ·  rank "
                                f"#{row['rank']} of {row['peers']}"
                                f"{' ' + row['group'] + ' loads' if row['group'] else ''}.  {src}")
        self.detail.grid()
        self.app.fit_window(self.app.LOADS_MIN_WIDTH, keep_position=True)

    def _set_price(self):
        if self.selected is None:
            return
        try:
            value = self._num(self.price_var, "Price", 0)
        except ValueError as exc:
            messagebox.showerror("Check your input", str(exc))
            return
        self.app.set_price(self.cat, self.selected, value)
        self.refresh()
        self._reselect()

    def _reset_price(self):
        if self.selected is None:
            return
        self.app.set_price(self.cat, self.selected, None)
        self.refresh()
        self._reselect()

    def _reselect(self):
        for iid, r in self.iid_row.items():
            if r["item"] is self.selected:
                self.tree.selection_set(iid)
                self._on_select()
                break


def main():
    if tk is None:
        sys.exit("Tkinter is not available. On Linux, install it with your package manager "
                 "(for example: sudo apt install python3-tk).")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
