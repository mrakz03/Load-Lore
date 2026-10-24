#!/usr/bin/env python3
"""
In Like Flint - Load Lore (formerly Cartridge Value Calculator) - a desktop tool for comparing ammunition by
performance.

Two tools, each split into categories (Centerfire Rifle, Handgun, Rimfire Rifle,
Shotgun):
  Load Dictionary  every factory load (and your handloads) of one cartridge, graded
                   S-F against each other on velocity, energy, recoil, cost, Taylor KO
                   and HITS. The grades can be switched off.
  Head to Head     2-5 loads side by side, from any cartridges in the category.

Data files (in data/ in the repo, or next to the program when packaged):
    loads_*.csv   the factory loads, one file per category
    ammo_*.csv    the cartridge list (cartridges with no factory loads can still
                  hold handloads)
Handloads are saved to my_handloads.csv.

Scoring: every factor is scored on a curve against the median load of the same
cartridge, then spread so the average load scores 70.

Ballistics: velocity at distance is computed by integrating the standard G1
drag model using each load's G1 ballistic coefficient. Recoil is an estimate
of free recoil energy for a gun of the weight you enter.

Requires only Python 3.9+ with Tkinter (included with the standard installers
for Windows and macOS).
"""

import base64
import bisect
import csv
import glob
import hashlib
import json
import math
import os
import re
import shutil
import ssl
import statistics
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
import webbrowser
import zlib
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
APP_TITLE = "In Like Flint - Load Lore"
APP_VERSION = "dev"             # the release build sets this from the git tag (v1.5 -> "1.5")
# Shown on the Settings page (web too, via build_web.py); the full text is LEGAL.md
ABOUT_TEXT = ("Calculated figures are estimates from makers' published velocities, approximate BCs "
              "and prices, and a simple ballistic model. Powder charges are NOT reloading data. Always "
              "confirm with the manufacturer's data and a current load manual before shooting or "
              "reloading. Brand names identify products only. No maker sponsors or endorses this "
              "software or is affiliated with its creator.\n\n"
              "Free software under the MIT License, provided as is, with no warranty.")
GRAINS_PER_OZ = 437.5
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
    "Winchester AutoComp", "Winchester WSF", "Winchester StaBall 6.5",
    "Accurate 2230", "Accurate 2460", "Accurate 2520", "Accurate 4350", "Accurate 5744",
    "Accurate No.2", "Accurate No.5", "Accurate No.7", "Accurate No.9",
    "Vihtavuori N140", "Vihtavuori N150", "Vihtavuori N160", "Vihtavuori N165",
    "Vihtavuori N133", "Vihtavuori N550", "Vihtavuori N320", "Vihtavuori N340",
    "Vihtavuori N350", "Ramshot Big Boy", "Ramshot TAC", "Ramshot X-Terminator",
    "Ramshot Enforcer", "Ramshot Silhouette", "Ramshot Competition", "Norma 202", "Norma 203B",
]
# metric key -> (display name, higher is better?)
METRICS = {
    "velocity": ("Velocity", True),
    "energy": ("Energy", True),
    "recoil": ("Recoil", False),
    "cost": ("Cost", False),
    "taylor": ("Taylor KO", True),      # Taylor Knock-Out factor (bullet weight x velocity x diameter)
    "hits": ("HITS", True),             # Hornady Index of Terminal Standards
}
TERMINAL_KEYS = ("taylor", "hits")     # need a bullet diameter, so they don't apply to shotshells
# Default scoring weights: velocity / energy / recoil / cost / Taylor KO / HITS.
# 3 / 3 / 1 / 3 / 3 / 3 -> about 19% each, recoil 6%. Shotshells have no Taylor KO / HITS
# (no bullet diameter), so the Shotgun category keeps those two at 0.
DEFAULT_WEIGHTS = (3, 3, 1, 3, 3, 3)

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
    payload_row: str = "Bullet weight"
    payload_col: str = "Grains"
    grain_style: bool = True     # labels read "ELD-M  ·  168 gr"; False = group + load text
    show_oz: bool = False        # also show payload in ounces (shotgun)
    legacy_filename: str = ""    # older file name to fall back to
    weights: tuple = DEFAULT_WEIGHTS   # velocity, energy, recoil, cost, Taylor KO, HITS
    loads_filename: str = ""     # manufacturer loads for the Load Dictionary / Head to Head
    step_yd: float = 100         # downrange / ballistic tables: 0, step, 2 x step ... 5 x step
    zero_yd: float = 100         # ballistic table: zero range
    sight_in: float = 1.5        # ballistic table: sight height over the bore (inches)
    terminal: bool = True        # show Taylor KO / HITS (needs a bullet diameter; not for shot)


CATEGORIES = (
    Category("Centerfire Rifle", "Hunting, precision and military rounds",
             "ammo_centerfire_rifle.csv", 100, 2000, 8.0, "RIFLE WEIGHT (LB)",
             legacy_filename="ammo_data.csv",
             loads_filename="loads_centerfire_rifle.csv"),
    Category("Handgun", "Pistol and revolver rounds",
             "ammo_handgun.csv", 10, 500, 2.0, "HANDGUN WEIGHT (LB)",
             loads_filename="loads_handgun.csv", step_yd=25, zero_yd=25, sight_in=0.6),
    Category("Rimfire Rifle", "Small-bore rimfire rounds",
             "ammo_rimfire_rifle.csv", 50, 500, 5.0, "RIFLE WEIGHT (LB)",
             weights=(3, 3, 1, 6, 3, 3),
             loads_filename="loads_rimfire_rifle.csv", step_yd=50, zero_yd=50),
    Category("Shotgun", "Birdshot, buckshot and slugs",
             "ammo_shotgun.csv", 25, 300, 7.5, "SHOTGUN WEIGHT (LB)",
             cartridge_label="GAUGE", payload_row="Payload",
             payload_col="Payload (gr)", grain_style=False, show_oz=True,
             terminal=False, weights=(3, 3, 1, 3, 0, 0),
             loads_filename="loads_shotgun.csv", step_yd=25, zero_yd=50, sight_in=0.6),
)


def version_text():
    return "Development Build" if APP_VERSION == "dev" else f"Development Build v{APP_VERSION}"


def default_weights(cat):
    return dict(zip(METRICS, cat.weights))


def metric_keys(cat):
    """The factors that apply to a category (shotshells have no bullet diameter)."""
    return [k for k in METRICS if cat.terminal or k not in TERMINAL_KEYS]


# The two tools: (key, title, blurb on the Home screen)
TOOLS = (("loads", "Load Dictionary", "Every load of a cartridge, factory or your own handload, "
                                      "graded against each other."),
         ("h2h", "Head to Head", "Put 2 to 5 loads side by side, even from different cartridges "
                                 "or categories."))
H2H_MIN, H2H_MAX = 2, 5
H2H_DISTANCE = 100       # Head to Head's starting distance (yd); each load is capped at its category's max


def tool_title(key):
    return next((t for k, t, _ in TOOLS if k == key), TOOLS[0][1])


def pick_key(cat, item):
    """How Head to Head remembers a load: its category, cartridge and handload id or label."""
    return (cat.title, item.cartridge, item.hid or item.label)


# Color themes (desktop and, via build_web.py, the phone/web version). "side" is the web
# sidebar / bottom bar; "scheme" tells the browser whether form controls should be light or dark.
THEMES = {
    "Classic": dict(bg="#0e1014", surface="#171a21", surface_2="#222732", border="#2d333f",
                    text="#e8eaee", muted="#8a93a3", accent="#4c8dff", accent_hover="#6aa0ff",
                    on_accent="#ffffff", side="#12151b", danger="#e5534b", hand="#5fd1b4", scheme="dark"),
    "Light": dict(bg="#f3f5f8", surface="#ffffff", surface_2="#e9edf3", border="#d3d9e2",
                  text="#161b24", muted="#5b6576", accent="#2563eb", accent_hover="#3b82f6",
                  on_accent="#ffffff", side="#ffffff", danger="#c62828", hand="#0f8a6c", scheme="light"),
    "Graphite": dict(bg="#121212", surface="#1c1c1c", surface_2="#282828", border="#383838",
                     text="#ededed", muted="#9e9e9e", accent="#d4d4d4", accent_hover="#ffffff",
                     on_accent="#121212", side="#171717", danger="#ef6b62", hand="#9be0c9", scheme="dark"),
    "Woodland camo": dict(bg="#0f120c", surface="#181d14", surface_2="#232a1c", border="#343e2a",
                          text="#e7eadf", muted="#98a088", accent="#8aa155", accent_hover="#a3ba6a",
                          on_accent="#10140b", side="#13170f", danger="#e0664f", hand="#c9b27c",
                          scheme="dark"),
    "Blaze": dict(bg="#121010", surface="#1c1917", surface_2="#28231f", border="#3a332c",
                  text="#f0ebe5", muted="#a69b8f", accent="#ff7a1a", accent_hover="#ff944a",
                  on_accent="#1a0d02", side="#161311", danger="#ff5a4f", hand="#5fd1b4", scheme="dark"),
    "Desert": dict(bg="#f4efe6", surface="#fffaf2", surface_2="#ece3d4", border="#d8ccb8",
                   text="#2b241b", muted="#74685a", accent="#9a6b2f", accent_hover="#b07d3a",
                   on_accent="#ffffff", side="#fbf5ea", danger="#b3392f", hand="#2f7d62", scheme="light"),
    "High contrast dark": dict(bg="#000000", surface="#000000", surface_2="#161616", border="#ffffff",
                               text="#ffffff", muted="#e6e6e6", accent="#ffd60a", accent_hover="#ffe45c",
                               on_accent="#000000", side="#000000", danger="#ff6b6b", hand="#7dfcc6",
                               scheme="dark"),
    "High contrast light": dict(bg="#ffffff", surface="#ffffff", surface_2="#ededed", border="#000000",
                                text="#000000", muted="#1f1f1f", accent="#0040c0", accent_hover="#002f8f",
                                on_accent="#ffffff", side="#ffffff", danger="#b00000", hand="#006b4f",
                                scheme="light"),
}
DEFAULT_THEME = "Classic"


def apply_theme(name):
    """Point the palette globals at a theme; screens built afterwards use it."""
    global BG, SURFACE, SURFACE_2, BORDER, TEXT, MUTED, ACCENT, ACCENT_HOVER, ON_ACCENT, DANGER, HAND_FG
    t = THEMES.get(name) or THEMES[DEFAULT_THEME]
    BG, SURFACE, SURFACE_2, BORDER = t["bg"], t["surface"], t["surface_2"], t["border"]
    TEXT, MUTED, ACCENT, ACCENT_HOVER = t["text"], t["muted"], t["accent"], t["accent_hover"]
    ON_ACCENT, DANGER, HAND_FG = t["on_accent"], t["danger"], t["hand"]


apply_theme(DEFAULT_THEME)

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


GRAVITY_MS2 = 9.80665
IN_PER_M = 39.37007874
WIND_MPH = 10.0
MS_PER_MPH = 0.44704


def _fly(muzzle_fps, bc_g1, start_y_m, angle, marks_m):
    """Point-mass flight in the vertical plane: G1 drag along the flight path plus gravity,
    RK2 midpoint steps of 0.5 m downrange. Returns {mark: (time s, height m)}, stopping where
    the bullet slows below 1 m/s."""
    v = muzzle_fps / FT_PER_M
    vx, vy = v * math.cos(angle), v * math.sin(angle)
    x, y, t, step, out = 0.0, start_y_m, 0.0, 0.5, {0.0: (0.0, start_y_m)}

    def deriv(vx, vy):                            # d/dx of (vx, vy, y, t)
        speed = math.hypot(vx, vy)
        k = _K * g1_cd(speed / SPEED_OF_SOUND_MS) * speed / bc_g1      # drag per metre
        return -k, -(k * vy + GRAVITY_MS2) / vx, vy / vx, 1.0 / vx

    for m in sorted(set(marks_m)):
        while x < m - 1e-12 and vx > 1.0:
            h = min(step, m - x)
            a = deriv(vx, vy)
            b = deriv(vx + 0.5 * h * a[0], vy + 0.5 * h * a[1])
            vx, vy = vx + h * b[0], vy + h * b[1]
            y, t, x = y + h * b[2], t + h * b[3], x + h
        if vx <= 1.0:
            break
        out[m] = (t, y)
    return out


def trajectory(muzzle_fps, bc_g1, sight_in, zero_yd, distances_yd):
    """[(time of flight s, path in)] at each distance, or None past where the bullet stops.
    The bore starts sight_in below the line of sight and is tilted up so the bullet crosses it
    again at zero_yd; path is above (+) or below (-) the line of sight. Gravity slows the bullet's
    rise and fall like the drag does (a true point-mass path, not the flat-fire t^2 drop, which
    read 10-15% too much drop at 400-500 yd against Hornady's published tables)."""
    marks = [d / YD_PER_M for d in distances_yd]
    zm, start = zero_yd / YD_PER_M, -sight_in / IN_PER_M
    angle = 0.0
    for _ in range(4):                            # aim: tilt by the miss over the zero range
        hit = _fly(muzzle_fps, bc_g1, start, angle, [zm]).get(zm)
        if hit is None:
            break
        angle -= hit[1] / zm
    flown = _fly(muzzle_fps, bc_g1, start, angle, marks)
    return [(flown[m][0], flown[m][1] * IN_PER_M) if m in flown else None for m in marks]


def ballistic_table(item, cat):
    """[(yards, velocity fps, energy ft-lbs, path in, 10 mph wind drift in)] from the muzzle out
    to 5 x cat.step_yd. Path is above (+) or below (-) the line of sight for a sight
    cat.sight_in above the bore zeroed at cat.zero_yd (point-mass G1 path in standard air);
    an estimate, not a full solver."""
    yards = []
    for n in range(6):
        yd = min(n * cat.step_yd, cat.max_distance)
        if yards and yd == yards[-1]:
            break
        yards.append(yd)
    v0 = item.muzzle_fps / FT_PER_M
    rows = []
    for yd, hit in zip(yards, trajectory(item.muzzle_fps, item.bc_g1, cat.sight_in, cat.zero_yd, yards)):
        if hit is None:
            break
        t, path = hit
        v = velocity_at(item.muzzle_fps, item.bc_g1, yd)
        drift = WIND_MPH * MS_PER_MPH * (t - (yd / YD_PER_M) / v0) * IN_PER_M   # Didion's lag rule
        rows.append((yd, v, energy_ftlbs(item.bullet_gr, v), path, drift))
    return rows


def energy_ftlbs(bullet_gr, velocity_fps):
    return bullet_gr * velocity_fps ** 2 / 450240.0


GAS_FPS = 4000.0      # powder gas velocity at the muzzle, for recoil


def recoil_ftlbs(bullet_gr, muzzle_fps, powder_gr, gun_lb):
    """Estimated free recoil energy (ft-lbs).

    The standard free-recoil formula: the gun takes the momentum of the bullet plus the powder
    gas, which leaves the muzzle at about 4000 fps. (It used to count the gas 1.75 times over,
    which read 40-60% above published recoil tables such as Chuck Hawks'.)
    """
    ejecta_momentum = (bullet_gr * muzzle_fps + powder_gr * GAS_FPS) / 7000.0
    gun_velocity = ejecta_momentum / gun_lb        # ft/s
    return 0.5 * (gun_lb / 32.174) * gun_velocity ** 2


# Typical gun weight (lb, loaded, scoped rifles) for cartridges far from their category's default:
# recoil is worked out for this weight unless you enter your own. A .50 BMG in the rifle default's
# 8 lb read 340+ ft-lbs; in its usual ~30 lb rifle it is about 95 (no muzzle brake).
GUN_LB = {     # per category: the same cartridge can be in a rifle and a handgun (.44 Magnum)
    "Centerfire Rifle": {
        ".50 BMG": 30.0, ".338 Lapua Magnum": 15.0, ".416 Remington Magnum": 10.0,
        ".458 Winchester Magnum": 10.0, ".458 Lott": 10.0, ".375 H&H Magnum": 9.5,
        ".375 Ruger": 9.5},
    "Handgun": {
        ".500 S&W Magnum": 4.5, ".460 S&W Magnum": 4.5, ".50 AE": 4.5, ".454 Casull": 3.5,
        ".480 Ruger": 3.5, ".44 Magnum": 3.0},
    "Shotgun": {"10 Gauge": 10.0},
}
GUN_LB_MAX = 60.0


def typical_gun_lb(cat, cartridge):
    return GUN_LB.get(cat.title, {}).get(cartridge, cat.default_gun_lb)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
# Cartridges that were renamed (metric names gained "mm"). Saved handloads, custom calibers and
# prices may still use the old names, so everything read from disk goes through canonical_name.
RENAMED_CARTRIDGES = {
    ".308 Winchester / 7.62x51 NATO": ".308 Winchester / 7.62x51mm NATO",
    ".223 Remington / 5.56 NATO": ".223 Remington / 5.56x45mm NATO",
    "5.45x39": "5.45x39mm", "5.7x28": "5.7x28mm", "6.5x55 Swedish": "6.5x55mm Swedish",
    "7.62x25 Tokarev": "7.62x25mm Tokarev", "7.62x39": "7.62x39mm", "7.62x54R": "7.62x54mmR",
    "8x57 Mauser": "8x57mm Mauser", "9.3x62": "9.3x62mm", "9x18 Makarov": "9x18mm Makarov",
}


# .223 Remington / 5.56x45mm NATO and .308 Winchester / 7.62x51mm NATO used to share one list each;
# since issue #28 the NATO loads are their own cartridges. Saved handloads under an old shared
# name go to the commercial cartridge, and a saved price is kept for both (its load is in one).
SPLIT_CARTRIDGES = {
    ".223 Remington / 5.56x45mm NATO": (".223 Remington", "5.56x45mm NATO"),
    ".308 Winchester / 7.62x51mm NATO": (".308 Winchester", "7.62x51mm NATO"),
}


def canonical_name(cartridge):
    cartridge = RENAMED_CARTRIDGES.get(cartridge, cartridge)
    return SPLIT_CARTRIDGES.get(cartridge, (cartridge,))[0]


# Bullet diameter (inches) per cartridge, for Taylor KO and HITS. Shotshells aren't listed.
DIAMETERS = {
    ".22-250 Remington": .224, ".223 Remington": .224, "5.56x45mm NATO": .224,
    ".224 Valkyrie": .224, ".243 Winchester": .243, ".25-35 Winchester": .257, "6mm ARC": .243,
    "6.5 Grendel": .264, ".260 Remington": .264, "6.5 Creedmoor": .264, "6.5 PRC": .264,
    ".270 Winchester": .277, "7mm-08 Remington": .284, ".277 Fury": .277, "6.8 Western": .277,
    "7mm Remington Magnum": .284, ".300 Blackout": .308, "7.62x39mm": .310, ".30-30 Winchester": .308,
    ".32-40 Winchester": .321, ".308 Winchester": .308, "7.62x51mm NATO": .308,
    ".30-06 Springfield": .308, ".300 Winchester Magnum": .308, ".300 PRC": .308,
    ".35 Remington": .358, ".348 Winchester": .348, ".350 Legend": .355, ".357 Magnum": .357,
    ".38-55 Winchester": .376, ".44 Magnum": .429, ".444 Marlin": .429, ".450 Bushmaster": .452,
    ".22 LR": .224, ".22 WMR": .224, ".25 ACP": .251, ".32 ACP": .312, ".32 H&R Magnum": .312,
    ".380 ACP": .355, "9mm Luger": .355, ".40 S&W": .400, "10mm Auto": .400, ".45 ACP": .451,
    ".38 Special": .357, ".45 Colt": .452, ".17 Mach 2": .172, ".17 HMR": .172, ".17 WSM": .172,
    ".22 Short": .224, ".22 Long": .224,
    # added later
    "5.45x39mm": 0.221,
    "6.5x55mm Swedish": 0.264,
    "8x57mm Mauser": 0.323,
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
    "9.3x62mm": 0.366,
    ".30-40 Krag": 0.308,
    ".357 SIG": 0.355,
    ".41 Magnum": 0.41,
    ".44 Special": 0.429,
    ".454 Casull": 0.452,
    ".460 S&W Magnum": 0.452,
    ".480 Ruger": 0.475,
    "5.7x28mm": 0.224,
    ".50 AE": 0.5,
    ".500 S&W Magnum": 0.5,
    "9x18mm Makarov": 0.365,
    ".327 Federal Magnum": 0.312,
    ".44-40 Winchester": 0.427,
    "7.62x54mmR": 0.311,
    "7.62x25mm Tokarev": 0.309,
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


def hits_index(bullet_gr, velocity_fps, diameter_in):
    """Hornady Index of Terminal Standards: (W^2 / 7000) x (V / D^2) / 100."""
    if diameter_in <= 0:
        return 0.0
    return (bullet_gr ** 2 / 7000.0) * (velocity_fps / diameter_in ** 2) / 100.0


def hits_class(h):
    """What size of animal a HITS number is meant for (Hornady's own bands)."""
    if h < 500:
        return "small game"
    if h <= 900:
        return "medium game"
    if h <= 1500:
        return "large game"
    return "dangerous game"


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
        return f"{item.load}  ·  {base}" if item.load else base
    if item.group and item.load:
        return f"{item.group}  ·  {item.load}"
    return item.load or f"{item.bullet_gr:g} gr"


PRESSURES = ("+P", "+P+")


def pressure_of(name):
    """'+P+', '+P' or '' from a load's name (Federal Train+Protect and +Peak aren't +P)."""
    if re.search(r"\+P\+", name or ""):
        return "+P+"
    return "+P" if re.search(r"\+P(?![A-Za-z+])", name or "") else ""


def icon_path():
    """assets/icon.png: bundled into the packaged app by PyInstaller (--add-data), or the
    repo's copy when running from a git checkout. None if it isn't there."""
    here = getattr(sys, "_MEIPASS", None)
    if here is None:
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    path = os.path.join(here, "icon.png")
    return path if os.path.exists(path) else None


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
            name = canonical_name(row.get("cartridge", ""))
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


def with_handload_only(groups, cartridge_loads):
    """Add an empty entry for every ammo_*.csv cartridge that has no factory loads (e.g.
    .32-40 Winchester), placed after the cartridge it follows there, so handloaders can still
    use the Load Dictionary for it."""
    order = list(dict.fromkeys(x.cartridge for x in cartridge_loads))
    if all(c in groups for c in order):
        return groups
    out = dict(groups)
    for i, c in enumerate(order):
        if c in out:
            continue
        prev = next((p for p in reversed(order[:i]) if p in out), None)
        keys = list(out)
        at = keys.index(prev) + 1 if prev else 0
        out = {k: out[k] for k in keys[:at]} | {c: []} | {k: out[k] for k in keys[at:]}
    return out


def read_settings():
    try:
        with open(os.path.join(app_dir(), SETTINGS_FILENAME), encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        if isinstance(data.get("prices"), dict):        # keys are "category|cartridge|load"
            data["prices"] = {new: v for k, v in data["prices"].items() for new in _rename_price_key(k)}
        elif "prices" in data:                          # a hand-edited file: setting a price would crash
            del data["prices"]
        return data
    except (OSError, ValueError):
        return {}


_OLD_LABEL = re.compile(r"^(\d+(?:\.\d+)?) gr  ·  (.+)$")


def _rename_price_key(key):
    """Update a saved price's key: old cartridge names, and loads saved when the label put the
    weight first ("150 gr  ·  Load", before v1.5) now read "Load  ·  150 gr". Returns a list:
    a price saved under a split cartridge (SPLIT_CARTRIDGES) is kept for both new ones."""
    parts = key.split("|", 2)
    if len(parts) != 3:
        return [key]
    m = _OLD_LABEL.match(parts[2])
    if m:
        parts[2] = f"{m.group(2)}  ·  {m.group(1)} gr"
    name = RENAMED_CARTRIDGES.get(parts[1], parts[1])
    return ["|".join([parts[0], c, parts[2]]) for c in SPLIT_CARTRIDGES.get(name, (name,))]


def _read_user_rows(path):
    """Rows of one of the user's own CSVs (lower-case keys), with old cartridge names updated."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(fh)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []
    for row in rows:
        if "cartridge" in row:
            row["cartridge"] = canonical_name(row["cartridge"])
    return rows


def write_settings(data):
    try:
        with open(os.path.join(app_dir(), SETTINGS_FILENAME), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass                                    # settings are a convenience, never fatal


# ---- updates (Settings > Updates): the newest GitHub release, installed in place ---- #
UPDATE_REPO = "mrakz03/Load-Lore"
REPO_PAGE = f"https://github.com/{UPDATE_REPO}"      # Settings > Source code (web too)
RELEASES_PAGE = f"{REPO_PAGE}/releases/latest"
LATEST_RELEASE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
SUMS_ASSET = "SHA256SUMS.txt"                      # made by the release job in CI
# release files carry the version: LoadLore-v1.7.4-Setup.exe / LoadLore-v1.7.4-Linux.tar.gz
# (v1.7.3-dev and older looked for CartridgeCalculator-*; those copies are reinstalled by hand)
ASSET_PREFIX = "LoadLore-"
ASSET_SUFFIX = {"windows": "-Setup.exe", "linux": "-Linux.tar.gz"}
PROGRAM = "LoadLore"                               # the Linux program, in a LoadLore folder in the tar
SHIPPED_DATA = ("ammo_*.csv", "loads_*.csv", BULLETS_FILENAME, "NOTICE.md", "DISCLAIMER.md")
# certificate bundles of the common Linux distros: the packaged app's OpenSSL was built on
# Ubuntu and only looks where Ubuntu keeps them, so on Fedora etc. it would find none
CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
              "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem", "/etc/pki/tls/cacert.pem")

# GitHub's mark (Octicons mark-github), 96x96 alpha, zlib + base64: drawn in the theme's text colour
GITHUB_MARK = (
    "eNrdmWtsVEUUxy8VA1uobdPWikKAVBRpbEFeiYEWMASSlprSkC7Io8bQuFEJkIKVRWnBxFhAIylQ2uoHio+tpmkDNqWg"
    "2bSRFEUFa4gUYalgCY/yKO2uqYVxubu9vTPn3Hvnzuwn/9/2nDO/3b0zd+acM4rCI8e05aWe1vZL3YR0X2pv9WxzTh2p"
    "REjD5+5oGyBAAydKXnxEGh69qqGPGKq3dpkUPbeOWKnPky0IH+G6SLj0R8FwAXzRVcKtTpdd+vwLxJbOzrBDT6whdnW/"
    "PIYbn9NNBHQlg4/+6B4ipoGtURz4CaeJsLxJlvjMO0RCl1Mt8Mv+IVLqyTTFv/2ASKrfbMd4h8jrQb7xwyGRUL/ROl3w"
    "b0T45O5kFJ/aRyKky4kIfuR5EjEdGwb51fSb0nLPFvGE95r+42aAd1LhtUHLtDWf8bFr184Khm+gbLMZ/Dj65zpD1rFV"
    "1vSvnw3FjqesPgfNb6QHaXvt5IPm9IbpGuJ3ylFG4fPpUb/oXCnN4RPkm+3OeaqWFNecCqi2X6fqAitpxgs6V/x12ldF"
    "ffnKhtL8NHa+UrLdX2ylLC6a8bPOtZv51++L5AN5DKRA8ySwb9ZGEf5LDOSc5illZ22TCH8xS8kLO0bfYj3vivCXspTB"
    "GXgLrLoqEf5GgJkbcvwEHCdF+DCnqVTtzyCvTbwA/zqg3FbtOxB+ln38GAST+9Dhg/Z6kedThOxNQfMUaPbFCSXc3wLQ"
    "vShs9ZA5Ygl9IjwAg9t0AzAeFS1H4Ey6lWG9wPi8KD8W5H7fKekA/714PbWTZfmV5SQimw++xREyoTRyjydYsoHsddGX"
    "rKVLpuBsZGlvgmy/VYb/CUsrB1VinQwfJMj1oNQ6IMMvYGkwTftAhp/N0tr7WctHMnz2jCd/g+W5X4a/mqUFAP+gDP91"
    "0GG5C3JrGT7Y4TrB+uyQ4YMz+NSf4AHJ8FtYWFMb4E8Rx0eB6TzkAfxXxflws/+4DJiqxflvwAPMZZC1COkHAFs6Bx7v"
    "OaL4pyEr2XEf2JpF+bBx5GPLJlXPieFj/IB0SFE+RcpjMf4+SHKB0k5VoQh+IQJKV5Q4pOUTEHjHnkSagoGHDbk25Hs7"
    "nrCdW/2IYNSV4kZbIDazlEkdGGW1+sfQnpg/3w4+pwdtBI1Qncfx0r9uPC99bC1O2B1yv6IZ/vL+pvd7uBL12F1GzYmU"
    "cERn+PP50YriWHhO37Zeb1FqJG44FjDCN4FTM9S1qaDXQMW6NJw9s6jyuFlv5WUtsmvwMmJFqAsK1vFJ+DeaLfvdQ7GF"
    "QxWZ2hf6kI2dxXOWGPY39JvcYfXzWaxQZlRijm/Rxy5ieicz8YVANxxvmvLpTbiecVBT4MXn17R1xrSQkm4zBUCxLrYE"
    "568wwV9gr/dyhnzzQqmkVlj6DNZnqgl/AYiuYAvIx91NXq/3yNpJRu9WgjG+DJmuds07nXPfMe5aYtETtT2wkZNvdJVy"
    "ZhQanqUFrOPj9+D4q09ZVk/rufi9KN6fbjhgaFGezuPg+1F+rsmILbrKYG+oHbzE/VW0nfl1mv4kF3ZYxhoEI/cpdzKt"
    "LsAQ/mPcv/9KquVDTesEo2J4+WfGcMxa3GF2WBwn/yjnFe2aW3zdUDrq5irudCaZvtdP4OHXJNhJmLK6dEMNbl0d+v04"
    "Q7GnaF1Wk2zJ3yaQbye9d8NifYb7nReLkwULnpVHBi/DUJWrJUqGIqH410rcDkPv9s8LY5X/t/4DeFtYRQ==")


def github_mark_png(size, colour):
    """The GitHub mark as a base64 PNG, `size` px square, in `colour` ("#rrggbb")."""
    src, n = zlib.decompress(base64.b64decode(GITHUB_MARK)), 96
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    raw = bytearray()
    for y in range(size):
        y0, y1 = y * n // size, max((y + 1) * n // size, y * n // size + 1)
        raw.append(0)                                   # PNG row filter: none
        for x in range(size):
            x0, x1 = x * n // size, max((x + 1) * n // size, x * n // size + 1)
            cells = [src[j * n + i] for j in range(y0, y1) for i in range(x0, x1)]
            raw += bytes((r, g, b, sum(cells) // len(cells)))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")



def version_tuple(text):
    """"v1.6.2" or "1.6.2" -> (1, 6, 2, 0, 1), for comparing; None for "dev" or anything that
    isn't a version. A suffix ("v1.7.2-dev", "1.8-beta") marks a test build: it sorts after
    the version before it and before the same number without a suffix (the last field 0 / 1)."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)([-+ ._]?[A-Za-z][\w.+-]*)?", (text or "").strip())
    if not m:
        return None
    nums = [int(x) for x in m.group(1).split(".")][:4]
    return tuple(nums + [0] * (4 - len(nums))) + (0 if m.group(2) else 1,)


def is_newer(latest, current):
    a, b = version_tuple(latest), version_tuple(current)
    return a is not None and b is not None and a > b


def _ssl_context():
    if sys.platform.startswith("linux") and not os.environ.get("SSL_CERT_FILE"):
        for path in CA_BUNDLES:
            if os.path.exists(path):
                return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def _http_get(url, timeout=20):
    """GET over HTTPS (certificates checked). Raises OSError on network problems."""
    req = urllib.request.Request(url, headers={"User-Agent": f"LoadLore/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return resp.read()


def latest_release():
    """The newest GitHub release: {version, page, assets: {file name: download url}}.
    Raises OSError (no connection) or ValueError (an answer we can't read)."""
    data = json.loads(_http_get(LATEST_RELEASE_API))
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise ValueError("GitHub's answer had no release version in it.")
    if version_tuple(data["tag_name"]) is None:
        raise ValueError(f"the newest release's tag ({data['tag_name']}) isn't a version number.")
    return {"version": data["tag_name"].strip().lstrip("v"),
            "page": data.get("html_url") or RELEASES_PAGE,
            "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets") or []
                       if isinstance(a, dict) and a.get("name") and a.get("browser_download_url")}}


def update_method():
    """How this copy can update itself: "windows" (run the new installer, which upgrades in
    place), "linux" (swap the files in place, like install.sh) or None (running from source,
    from the Windows zip, or a folder we can't write to): then Update opens the releases page."""
    if not getattr(sys, "frozen", False) or version_tuple(APP_VERSION) is None:
        return None
    here = os.path.dirname(sys.executable)
    try:
        if sys.platform == "win32":                # the installer leaves unins000.exe beside the app
            return "windows" if glob.glob(os.path.join(here, "unins*.exe")) else None
        if sys.platform.startswith("linux"):
            return "linux" if os.access(here, os.W_OK) else None
    except OSError:
        pass
    return None


def release_asset(release, method):
    """The file of `release` to install for `method` ("windows" / "linux"): the one named with the
    release's version, else any LoadLore-*-Setup.exe / -Linux.tar.gz."""
    assets, suffix = release["assets"], ASSET_SUFFIX[method]
    exact = f"{ASSET_PREFIX}v{release['version']}{suffix}"
    if exact in assets:
        return exact
    named = sorted(n for n in assets if n.startswith(ASSET_PREFIX) and n.endswith(suffix))
    if named:
        return named[-1]
    raise ValueError(f"Release v{release['version']} has no {exact}.")


def download_verified(release, name, folder):
    """Download one file of a release into `folder` and check it against the release's
    SHA256SUMS.txt. Returns its path. Raises ValueError if it's missing or doesn't match."""
    assets = release["assets"]
    for need in (name, SUMS_ASSET):
        if need not in assets:
            raise ValueError(f"Release v{release['version']} has no {need}.")
    sums = {}
    for line in _http_get(assets[SUMS_ASSET]).decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    if name not in sums:
        raise ValueError(f"{SUMS_ASSET} has no checksum for {name}.")
    data = _http_get(assets[name], timeout=60)
    if hashlib.sha256(data).hexdigest() != sums[name]:
        raise ValueError("The download didn't match its checksum, so nothing was installed.")
    path = os.path.join(folder, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def install_linux_update(tar_path, program):
    """Unpack a Linux release over the copy at `program` (the LoadLore file): the program first,
    copied under a temporary name and renamed (the running one can't be written over), then the
    data files. The user's own files (my_*.csv, settings.json) aren't in the tar and are left
    alone. Returns the program to start."""
    here = os.path.dirname(program)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp, filter="data")
        src = os.path.join(tmp, PROGRAM)
        new_data = [f for f in glob.glob(os.path.join(src, "*.csv"))
                    if not os.path.basename(f).startswith("my_")]
        if not os.path.isfile(os.path.join(src, PROGRAM)) or \
                not any(os.path.basename(f).startswith("loads_") for f in new_data):
            raise ValueError("The download doesn't look like a Load Lore release.")
        part = program + ".new"
        shutil.copyfile(os.path.join(src, PROGRAM), part)
        os.chmod(part, 0o755)
        os.replace(part, program)
        keep = {os.path.basename(f) for f in new_data}
        for f in new_data:
            shutil.copyfile(f, os.path.join(here, os.path.basename(f)))
        for pattern in SHIPPED_DATA:               # files an older release shipped and this one drops
            for f in glob.glob(os.path.join(here, pattern)):
                if os.path.basename(f) not in keep:
                    os.remove(f)
        for name in ("icon.png", "LICENSE", "LEGAL.md"):
            if os.path.exists(os.path.join(src, name)):
                shutil.copyfile(os.path.join(src, name), os.path.join(here, name))
    return program


def _update_error(what, err):
    """One line for the Updates card: network trouble in plain words, our own ValueErrors as is."""
    if isinstance(err, ValueError):
        return f"{what}: {err}"
    if isinstance(err, urllib.error.HTTPError):    # GitHub answered, but not with a release
        if err.code == 404:                        # also what a private repository answers
            return f"{what}: GitHub has no public release to check against."
        if err.code in (403, 429):
            return f"{what}: GitHub is limiting checks right now. Try again in an hour."
        return f"{what}: GitHub answered with error {err.code}. Try again later."
    if isinstance(getattr(err, "reason", None), ssl.SSLError):
        return f"{what}: couldn't verify GitHub's security certificate."
    if isinstance(err, OSError) and not isinstance(err, PermissionError):
        return f"{what}: couldn't reach GitHub. Check your internet connection."
    return f"{what}: {err}"


def _launch_env():
    """Environment for starting a new copy of the packaged app (directly, or through the
    installer): without PYINSTALLER_RESET_ENVIRONMENT the new copy would take the running
    one's unpacked files for its own, and on Linux LD_LIBRARY_PATH goes back to the user's."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = orig
    return env


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
    return _read_user_rows(os.path.join(app_dir(), HANDLOAD_FILENAME))


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
        "hits": hits_index(item.bullet_gr, v, d),
    }


# The Load Dictionary grades loads of the SAME cartridge against each other. They are all close
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


def score_loads(items, distance_yd, gun_lb, weights, costs, by_type=False):
    """Grade loads of one cartridge against each other (the Load Dictionary's grades; Head to
    Head shows the same ones). `costs` is the price per round of each item. Shotshells
    (by_type) are only graded against their own load type (Target vs Target, Slug vs Slug).
    Returns one dict per item: stats, scores, overall, grade, rank, peers, group."""
    stats = [compute_stats(x, distance_yd, gun_lb, c) for x, c in zip(items, costs)]
    keys = [x.group if by_type else "" for x in items]
    rows = [None] * len(items)
    for key in dict.fromkeys(keys):
        idx = [i for i, k in enumerate(keys) if k == key]
        for i, (sc, overall) in zip(idx, relative_scores([stats[i] for i in idx], weights)):
            rows[i] = dict(item=items[i], stats=stats[i], scores=sc, overall=overall,
                           grade=grade_relative(overall), group=key, peers=len(idx))
        for n, i in enumerate(sorted(idx, key=lambda i: -rows[i]["overall"]), start=1):
            rows[i]["rank"] = n
    return rows


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


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class App:
    """Owns the window, the theme, and switching between the picker and calculators."""

    WIN_W, WIN_H = 1360, 860      # default window size (clamped to small screens); resizable
    MIN_W, MIN_H = 980, 600
    SIDEBAR_W = 210

    def __init__(self, root):
        self.root = root
        self.settings = read_settings()
        self.theme = self.settings.get("theme") if self.settings.get("theme") in THEMES else DEFAULT_THEME
        apply_theme(self.theme)
        try:
            self.scale = min(1.6, max(0.85, float(self.settings.get("text_scale", 1.0))))
        except (TypeError, ValueError):
            self.scale = 1.0
        # pixel sizes grow with the screen DPI like the point-sized fonts do (96 dpi = 1.0)
        try:
            self.dpi = max(1.0, float(root.tk.call("tk", "scaling")) * 72 / 96)
        except (tk.TclError, ValueError):
            self.dpi = 1.0
        self.view = None
        self._fonts, self._widths = {}, {}   # text_width caches
        self._base_w = self._auto_w = None   # window width before / after grow_to_fit
        self._wm_shift = (0, 0)   # how far the window manager moves the window we place (Wayland)
        families = set(tkfont.families(root))
        self.family = next((f for f in ("Segoe UI", "SF Pro Text", "Inter", "Noto Sans",
                                        "Cantarell", "Ubuntu", "Helvetica Neue", "Helvetica",
                                        "Arial", "DejaVu Sans") if f in families), "TkDefaultFont")
        root.configure(bg=BG)
        try:                                   # window / taskbar icon instead of Tk's feather
            big = tk.PhotoImage(file=icon_path())                    # 1024 px master
            self._icons = (big.subsample(4), big.subsample(16))       # 256 and 64 px
            root.iconphoto(True, *self._icons)
        except (tk.TclError, TypeError):
            pass
        self._style()

        # load every category's data up front so the picker can show counts
        self.data = {}      # title -> dict(loads=[...], problems=[...], error="")
        self.hand_rows = read_handload_rows()
        self.bullets = read_bullets()
        for cat in CATEGORIES:
            self.data[cat.title] = self._load_category(cat)

        self.stage = None
        self.mode = "home"                # home / loads / h2h
        self.cat = None
        self.carry = {}                   # per category: what each tab knew when you left it
        self.h2h = []                     # the Head to Head picks (pick_key), any category
        self.h2h_snap = {}                # what Head to Head had on screen when you left it
        self._place_window()
        self._build_shell()
        self.show_launcher()
        root.bind_all("<Control-Key-1>", lambda e: self.go_mode("loads"))
        root.bind_all("<Control-Key-2>", lambda e: self.show_h2h())
        root.bind_all("<Control-Key-0>", lambda e: self.show_launcher())
        self.upd = {"state": "idle"}      # Settings > Updates: idle/checking/latest/available/downloading/error
        if self.check_on_start and version_tuple(APP_VERSION):
            root.after(2000, lambda: self.check_updates(on_start=True))

    # ---- data ------------------------------------------------------------ #
    def _load_category(self, cat):
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
        """The category's handloads. One whose label is already taken in its cartridge (a
        duplicate with no name of its own) gets " (2)", " (3)"... like the web version, so each
        can be told apart and picked in Head to Head."""
        out = []
        if not cat.grain_style:
            return out
        taken = {(x.cartridge, x.label) for x in self.data[cat.title]["detail"]}
        for row in self.hand_rows:
            if row.get("category") != cat.title:
                continue
            try:
                item = load_from_handload_row(row, cat.grain_style)
            except (KeyError, ValueError):
                continue
            base, n = item.label, 1
            while (item.cartridge, item.label) in taken:
                n += 1
                item.label = f"{base} ({n})"
            taken.add((item.cartridge, item.label))
            out.append(item)
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

    # ---- S-F grades on / off (both tools; remembered) ---------------------- #
    @property
    def show_grades(self):
        return self.settings.get("show_grades", True) is not False

    def set_show_grades(self, on):
        self.settings["show_grades"] = bool(on)
        write_settings(self.settings)

    # ---- Head to Head picks ------------------------------------------------ #
    def add_to_h2h(self, cat, item):
        """Add a load to the Head to Head list. Returns the new count, or None if it was
        already there or the list is full."""
        key = pick_key(cat, item)
        if key in self.h2h or len(self.h2h) >= H2H_MAX:
            return None
        self.h2h.append(key)
        return len(self.h2h)

    def dict_weights(self, cat):
        """The category's scoring weights as last set in its Load Dictionary (else the
        defaults), so Head to Head grades each load the way the dictionary does."""
        out = default_weights(cat)
        for k, v in self.carry.get(cat.title, {}).get("weights", {}).items():
            try:
                if k in out and 0 <= float(v) <= 10:
                    out[k] = float(v)
            except (TypeError, ValueError):
                pass
        return out

    # ---- prices you set yourself -------------------------------------------- #
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
        """Scale a pixel measurement with the text size and the screen DPI."""
        return int(round(n * self.scale * self.dpi))

    def set_scale(self, new_scale):
        """Text size A- / A+. Rebuilds the current screen and keeps what was entered."""
        new_scale = round(min(1.6, max(0.85, new_scale)), 2)
        if new_scale == self.scale:
            return
        self.scale = new_scale
        self.settings["text_scale"] = new_scale
        write_settings(self.settings)
        self._rebuild()

    def set_theme(self, name):
        """Appearance picker. Rebuilds the current screen in the new colors."""
        if name not in THEMES or name == self.theme:
            return
        self.theme = name
        self.settings["theme"] = name
        write_settings(self.settings)
        apply_theme(name)
        self.root.configure(bg=BG)
        self._rebuild()

    def _rebuild(self):
        snap = self.view.snapshot() if self.view is not None else None
        cat = self.view.cat if self.view is not None else None
        tab = getattr(self.view, "tab", "loads")
        self._style()
        self._build_shell()                          # sidebar / tabs pick up the new size too
        if cat is None:
            if self.mode == "home":
                self.show_launcher()
            elif self.mode == "settings":
                self.show_settings()
            elif self.mode == "h2h":
                self.h2h_snap.update(snap or {})
                self.view = None
                self.show_h2h()
            else:
                self.show_picker(self.mode)
        else:
            self.open_category(cat, tab, snap)

    def _style(self):
        r = self.root
        s = ttk.Style(r)
        s.theme_use("clam")
        r.option_add("*TCombobox*Listbox.background", SURFACE_2)
        r.option_add("*TCombobox*Listbox.foreground", TEXT)
        r.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        r.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)
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
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", ON_ACCENT)])
        s.map("Treeview.Heading", background=[("active", BORDER)])

    def label(self, parent, text="", size=11, color=None, bold=False, bg=None, **kw):
        return tk.Label(parent, text=text, bg=SURFACE if bg is None else bg,
                        fg=TEXT if color is None else color, font=self.f(size, bold), **kw)

    def button(self, parent, text, command, kind="secondary"):
        if kind == "primary":
            bg, fg, hover = ACCENT, ON_ACCENT, ACCENT_HOVER
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
        calls so columns never shrink while filtering. The stretch column fits its longest
        entry (full load names) and takes any spare room."""
        head, body = self.f(10, True), self.f(10)
        pad = self.text_width(body, "00") + 14
        known = {} if known is None else known
        for i, col in enumerate(cols):
            need = max([self.text_width(head, col)]
                       + self.widest(body, {str(r[i]) for r in rows})) + pad
            known[col] = max(known.get(col, 0), need)
            if col == stretch_col:
                tree.column(col, width=known[col], minwidth=min(known[col], self.text_width(body, "0" * 24)),
                            stretch=True)
            else:
                tree.column(col, width=known[col], minwidth=known[col], stretch=False)
        return known

    def text_width(self, font, text):
        """Pixel width of `text` in `font` (an f() tuple), remembered: a Tk measure call is slow
        (about half a millisecond), and a table re-measures the same names on every redraw."""
        key = (font, text)
        w = self._widths.get(key)
        if w is None:
            f = self._fonts.get(font)
            if f is None:
                f = self._fonts[font] = tkfont.Font(font=font)
            w = self._widths[key] = f.measure(text)
        return w

    def widest(self, font, texts):
        """Exact widths of the few strings that can be the widest of `texts`. Each string is
        first estimated from its letters' widths (measured once per letter), then the top few
        are measured for real, so a column of 1,000 load names costs a handful of measures."""
        texts = list(texts)
        if len(texts) <= 8:
            return [self.text_width(font, t) for t in texts]
        est = sorted(texts, key=lambda t: sum(self.text_width(font, ch) for ch in t), reverse=True)
        return [self.text_width(font, t) for t in est[:8]]

    def grow_to_fit(self, extra):
        """Resize the window by `extra` px so a table fits, within the screen. It widens for a
        wide table and gives the room back for a narrower one later, but never goes below the
        width the user last chose (a width this method didn't set counts as the user's)."""
        r = self.root
        if r.state() == "zoomed":
            return
        cur = r.winfo_width()
        base = self._base_w if cur == self._auto_w else cur
        w = max(base, min(cur + extra, r.winfo_screenwidth() - 20))
        if w != cur:
            # The window should only change size (issue #3). wm_geometry gives the outer
            # position, which is what setting it expects (winfo_x / winfo_y is the inside, under
            # the title bar). Some window managers still move it: on KDE Wayland with Tk 9 every
            # resize put it a title bar lower. So check where it landed, put it back, and
            # remember the shift so later resizes ask for the right place straight away.
            m = re.search(r"[+-](-?\d+)[+-](-?\d+)$", r.wm_geometry())
            fx, fy = (int(m[1]), int(m[2])) if m else (r.winfo_x(), r.winfo_y())
            x = max(0, min(fx, r.winfo_screenwidth() - w - 10))
            x0, y0 = r.winfo_rootx() + x - fx, r.winfo_rooty()   # where the inside should end up
            sx, sy = self._wm_shift
            moved = x != fx or self._wm_shift != (0, 0)
            r.geometry(f"{w}x{r.winfo_height()}" + (f"+{x - sx}+{fy - sy}" if moved else ""))
            r.update_idletasks()
            dx, dy = r.winfo_rootx() - x0, r.winfo_rooty() - y0
            if dx or dy:
                self._wm_shift = (sx + dx, sy + dy)
                r.geometry(f"+{x - sx - dx}+{fy - sy - dy}")
                r.update_idletasks()
        self._base_w, self._auto_w = base, r.winfo_width()

    # ---- window + shell --------------------------------------------------- #
    def _place_window(self):
        """Comfortable default size, centred; the window can be resized from there."""
        r = self.root
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = min(int(self.WIN_W * self.dpi), sw - 40)
        h = min(int(self.WIN_H * self.dpi), sh - 90)
        r.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        r.minsize(min(int(self.MIN_W * self.dpi), w), min(int(self.MIN_H * self.dpi), h))
        r.resizable(True, True)
        r.title(APP_TITLE)

    def fit_window(self):
        """The window keeps its size; the page scrolls if it is taller. Refresh the scroll area."""
        self._update_scroll()

    def _refit_soon(self):
        """After a window resize, let the open screen re-fit its table height (once, when idle)."""
        if getattr(self, "_refit_pending", False):
            return
        self._refit_pending = True

        def run():
            self._refit_pending = False
            fit = getattr(self.view, "fit_table_height", None)
            if fit is not None:
                fit()
        self.root.after_idle(run)

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
        self.foot = tk.Frame(self.sidebar, bg=SURFACE)     # Settings, at the bottom left
        self.foot.pack(side="bottom", fill="x", padx=12, pady=14)
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
                                                   self._update_scroll(), self._refit_soon()))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._on_wheel)
            # Tk's dropdowns step their value on every wheel tick, and each step re-ran the
            # theme or cartridge change (issue #14): over a closed dropdown the wheel scrolls the page
            self.root.bind_class("TCombobox", seq, lambda e: (self._on_wheel(e), "break")[1])
        self._draw_chrome()

    def _sidebar_width(self):
        """Wide enough for the longest menu entry at the current text size and screen DPI."""
        main, sub = tkfont.Font(font=self.f(11, True)), tkfont.Font(font=self.f(10, True))
        title, ver = tkfont.Font(font=self.f(17, True)), tkfont.Font(font=self.f(8))
        need = max([main.measure(t) for _, t, _ in TOOLS] + [title.measure("Load Lore") - 12]
                   + [ver.measure(version_text()) - 12]
                   + [sub.measure(cat.title) + 16 for cat in CATEGORIES])
        return max(self.px(self.SIDEBAR_W), need + 2 * 12 + 2 * 12 + 10)   # label + nav padding

    def _on_wheel(self, e):
        """Scroll the page with the mouse wheel (tables and lists keep their own wheel)."""
        if getattr(self, "search_popup", None) is not None:
            if isinstance(e.widget, tk.Listbox) and e.widget is self.search_popup.listbox:
                return
            self.search_popup.close()         # the load search list would stay put as the page moved
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

    def _nav_button(self, text, command, active, sub=False, parent=None):
        bg = ACCENT if active else SURFACE
        hover = ACCENT if active else SURFACE_2
        fg = ON_ACCENT if active else (MUTED if sub else TEXT)
        box = tk.Frame(parent or self.nav, bg=bg, cursor="hand2")
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
        for w in self.nav.winfo_children() + self.foot.winfo_children():
            w.destroy()
        self.label(self.nav, "In Like Flint", 11, MUTED, True, bg=SURFACE, anchor="w").pack(
            anchor="w", padx=6)
        self.label(self.nav, "Load Lore", 17, TEXT, True, bg=SURFACE, anchor="w").pack(
            anchor="w", padx=6)
        self.label(self.nav, version_text(), 8, MUTED, bg=SURFACE, anchor="w").pack(
            anchor="w", padx=6, pady=(2, 18))
        self._nav_button("Settings", self.show_settings, self.mode == "settings",
                         parent=self.foot)
        self._nav_button("Home", self.show_launcher, self.mode == "home")
        for key, text, _ in TOOLS:
            if key == "h2h":                  # one page for every category: no category list
                self._nav_button(text, self.show_h2h, self.mode == key)
                continue
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
        self._stash()
        self.mode, self.cat, self.view = "home", None, None
        stage = self._new_stage()
        self.root.title(APP_TITLE)
        self._draw_chrome()
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="x", padx=36, pady=(40, 28))
        self.label(wrap, "In Like Flint", 15, MUTED, True, bg=BG, anchor="w").pack(anchor="w")
        self.label(wrap, "Load Lore", 26, TEXT, True, bg=BG, anchor="w").pack(anchor="w")
        self.label(wrap, "Grade ammo from S to F on velocity, energy, recoil and cost, or put "
                   "loads head to head.", 12, MUTED,
                   bg=BG, anchor="w").pack(anchor="w", pady=(4, 26))
        feats = tk.Frame(wrap, bg=BG)
        feats.pack(fill="x")
        feats.columnconfigure((0, 1), weight=1, uniform="f")
        for i, (key, title, blurb) in enumerate(TOOLS):
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

    # ---- updates (Settings > Updates) -------------------------------------- #
    @property
    def check_on_start(self):
        return self.settings.get("check_updates") is True

    def set_check_on_start(self, on):
        self.settings["check_updates"] = bool(on)
        write_settings(self.settings)

    def _in_background(self, work, done):
        """Run work() off the Tk thread (it waits on the network), then done(result, error) on it."""
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception as exc:               # any failure is shown, never fatal
                box["error"] = exc
        t = threading.Thread(target=run, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                self.root.after(150, poll)
            else:
                done(box.get("result"), box.get("error"))
        self.root.after(150, poll)

    def _set_update(self, **state):
        self.upd = state
        if self.mode == "settings":
            self.show_settings()

    def check_updates(self, on_start=False):
        if self.upd["state"] in ("checking", "downloading"):
            return
        if not on_start:
            self._set_update(state="checking")

        def done(rel, err):
            if err is not None:
                if not on_start:
                    self._set_update(state="error", message=_update_error("Couldn't check for updates", err))
                return
            if not is_newer(rel["version"], APP_VERSION):
                if not on_start:
                    self._set_update(state="latest", release=rel)
                return
            self._set_update(state="available", release=rel)
            if on_start and messagebox.askyesno(
                    "Update available", f"Load Lore v{rel['version']} is available (you have "
                    f"v{APP_VERSION}). Update now?\n\nYou can also update later from Settings."):
                self.start_update()
        self._in_background(latest_release, done)

    def start_update(self):
        rel, method = self.upd.get("release"), update_method()
        if rel is None:
            return
        if method is None:
            webbrowser.open(rel["page"])
            return
        if not messagebox.askyesno(
                "Update Load Lore", f"Download and install v{rel['version']}? The app closes and "
                "opens again by itself. Your handloads, prices and settings are kept."):
            return
        self._set_update(state="downloading", release=rel)
        folder = tempfile.mkdtemp(prefix="loadlore-update-")

        def work():
            path = download_verified(rel, release_asset(rel, method), folder)
            if method == "linux":
                path = install_linux_update(path, sys.executable)    # the program to start
                shutil.rmtree(folder, ignore_errors=True)
            return path

        def done(path, err):
            if err is not None:
                shutil.rmtree(folder, ignore_errors=True)
                self._set_update(state="error", release=rel, message=_update_error("Update failed", err))
                return
            try:
                if method == "windows":            # upgrades in place, then starts the new version
                    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                      "/CLOSEAPPLICATIONS"], env=_launch_env())
                else:
                    subprocess.Popen([path], cwd=os.path.dirname(path),
                                     env=_launch_env(), start_new_session=True)
            except OSError as exc:
                self._set_update(state="error", release=rel, message=(
                    f"Updated, but couldn't restart: {exc}. Close and reopen the app."
                    if method == "linux" else f"Couldn't start the installer: {exc}"))
                return
            self.root.destroy()
        self._in_background(work, done)

    def _updates_row(self, row):
        """The Updates card on the Settings page: status, Check / Update button, start-up switch."""
        u, rel = self.upd, self.upd.get("release")
        if version_tuple(APP_VERSION) is None:     # running from source, or a test build from Actions
            note = ("Test build: install a release to get updates" if getattr(sys, "frozen", False)
                    else "This copy runs from source: update it with git pull")
            self.button(row("Updates", note),
                        "Releases page", lambda: webbrowser.open(RELEASES_PAGE)).pack()
            return
        notes = {"idle": f"You have v{APP_VERSION}",
                 "checking": "Checking GitHub for a newer version…",
                 "latest": f"You have the newest version (v{APP_VERSION})",
                 "available": f"v{rel and rel['version']} is available (you have v{APP_VERSION})",
                 "downloading": f"Downloading v{rel and rel['version']}…",
                 "error": u.get("message", "")}
        box = row("Updates", notes[u["state"]])
        if u["state"] == "available":
            text = f"Update to v{rel['version']}" if update_method() else "Download"
            self.button(box, text, self.start_update, "primary").pack(side="left", padx=(0, 10))
        else:
            b = self.button(box, "Check for updates", self.check_updates)
            if u["state"] in ("checking", "downloading"):
                b.config(state="disabled", cursor="")
            b.pack(side="left", padx=(0, 10))
        self.label(box, "Check at start", 10, MUTED, bg=SURFACE).pack(side="left", padx=(6, 6))
        chip = tk.Label(box, font=self.f(10, True), padx=10, pady=3, cursor="hand2", width=4)

        def flip(e=None):
            self.set_check_on_start(not self.check_on_start)
            paint()

        def paint():
            on = self.check_on_start
            chip.config(text="On" if on else "Off", bg=ACCENT if on else SURFACE_2,
                        fg=ON_ACCENT if on else TEXT)
        paint()
        chip.bind("<Button-1>", flip)
        chip.pack(side="left")

    def _github_button(self, parent):
        """A small GitHub logo that opens the repo page (Settings > Source code)."""
        img = tk.PhotoImage(data=github_mark_png(self.px(26), TEXT))
        b = tk.Label(parent, image=img, bg=SURFACE, cursor="hand2", padx=self.px(7),
                     pady=self.px(7))
        b.image = img                                   # Tk drops images nobody holds
        b.bind("<Button-1>", lambda e: webbrowser.open(REPO_PAGE))
        b.bind("<Enter>", lambda e: b.config(bg=SURFACE_2))
        b.bind("<Leave>", lambda e: b.config(bg=SURFACE))
        return b

    def show_settings(self):
        """Settings (bottom of the sidebar): theme, text size, the S-F grades switch and updates."""
        self._stash()
        self.mode, self.cat, self.view = "settings", None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — Settings")
        self._draw_chrome()
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="x", padx=36, pady=(32, 28))
        self.label(wrap, "Settings", 22, TEXT, True, bg=BG, anchor="w").pack(anchor="w", pady=(0, 6))

        def section(title):
            """A titled box; its rows are split by thin lines instead of each having a box."""
            self.label(wrap, title, 11, MUTED, True, bg=BG, anchor="w").pack(
                anchor="w", pady=(10, 6))
            card = tk.Frame(wrap, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
            card.pack(fill="x", pady=(0, 12))
            card.rows = 0
            return card

        def line(card):
            if card.rows:
                tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=20)
            card.rows += 1

        def row(title, note):
            line(card)
            r = tk.Frame(card, bg=SURFACE)
            r.pack(fill="x")
            text = tk.Frame(r, bg=SURFACE)
            text.pack(side="left", fill="x", expand=True, padx=20, pady=14)
            self.label(text, title, 12, TEXT, True, bg=SURFACE, anchor="w").pack(anchor="w")
            self.label(text, note, 10, MUTED, bg=SURFACE, anchor="w").pack(anchor="w", pady=(2, 0))
            right = tk.Frame(r, bg=SURFACE)
            right.pack(side="right", padx=20, pady=14)
            return right

        card = section("Display")
        theme_var = tk.StringVar(value=self.theme)
        pick = ttk.Combobox(row("Theme", "Colors for the whole app"), textvariable=theme_var,
                            values=list(THEMES), state="readonly", font=self.f(11),
                            width=max(len(n) for n in THEMES) + 2)
        pick.pack()
        pick.bind("<<ComboboxSelected>>", lambda e: self.set_theme(theme_var.get()))
        box = row("Text size", f"{round(self.scale * 100)}%")
        for text, delta in (("A−", -0.15), ("A+", 0.15)):
            b = tk.Label(box, text=text, bg=SURFACE_2, fg=TEXT, font=self.f(11, True),
                         padx=12, pady=4, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, d=delta: self.set_scale(self.scale + d))
        def flip():
            self.set_show_grades(not self.show_grades)
            style_grades_chip(self, chip)
        chip = grades_chip(self, row("S–F grades", "Show the grades in the Load Dictionary and "
                                     "Head to Head"), flip)
        chip.pack()
        card = section("About")
        self._updates_row(row)
        self._github_button(row("Source code", "Free and open source: code, issues and "
                                "releases on GitHub")).pack()
        line(card)
        self.label(card, "Disclaimer", 12, TEXT, True, bg=SURFACE, anchor="w").pack(
            anchor="w", padx=20, pady=(14, 0))
        about = self.label(card, ABOUT_TEXT, 10, MUTED, bg=SURFACE, anchor="w", justify="left")
        about.pack(fill="x", padx=20, pady=(2, 14))
        about.bind("<Configure>", lambda e: about.configure(wraplength=max(e.width, 1)))
        self.label(wrap, version_text(), 10, MUTED, bg=BG, anchor="w").pack(anchor="w", pady=(2, 0))
        self._update_scroll()

    def _stash(self):
        """Remember what the open tool has on screen, for when you come back to it."""
        if self.view is None:
            return
        if self.view.tab == "h2h":
            self.h2h_snap.update(self.view.snapshot())
        elif self.cat is not None:
            self.carry.setdefault(self.cat.title, {}).update(self.view.snapshot())

    def show_h2h(self):
        """Head to Head: one page for loads of every category."""
        self._stash()
        self.mode, self.cat, self.view = "h2h", None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {tool_title('h2h')}")
        self._draw_chrome()
        self.view = HeadToHeadView(self, stage, dict(self.h2h_snap) or None)
        self._update_scroll()

    def show_picker(self, mode):
        """Choose a category for the Load Dictionary (Head to Head has no categories)."""
        if mode == "h2h":
            return self.show_h2h()
        self._stash()
        self.mode, self.cat, self.view = mode, None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {tool_title(mode)}")
        self._draw_chrome()
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="x", padx=36, pady=(32, 28))
        self.label(wrap, tool_title(mode), 22,
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
                shown = info["detail"]
                carts = {x.cartridge for x in shown}
                if cat.grain_style:                          # + cartridges open to handloads only
                    carts |= {x.cartridge for x in info["loads"]}
                caption = f"{len(carts)} cartridges  ·  {len(shown):,} loads"
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
        title = tool_title(active)
        self.label(box, f"{title}  ·  {cat.title}", 20, TEXT, True, bg=BG).grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        return box

    def go(self, cat, tab):
        """Open a category in a feature, remembering what each tab had on screen."""
        if tab == "h2h":
            return self.show_h2h()
        self._stash()
        mem = self.carry.get(cat.title)
        self.open_category(cat, tab, dict(mem) if mem else None)

    def go_mode(self, tab):
        self.show_picker(tab)

    def open_category(self, cat, tab="loads", snap=None):
        """Open a category's tool, set up from `snap` (what it had on screen last time) so the
        table is computed and drawn once, not once with the defaults and again restored."""
        info = self.data[cat.title]
        if info["error"]:
            messagebox.showerror("Can't open this category", info["error"] +
                                 f"\n\nExpected next to the program:\n{app_dir()}")
            return
        if info["problems"]:
            messagebox.showwarning("Some rows were skipped", "\n".join(info["problems"][:15]))
            info["problems"] = []                   # only warn once
        self.cat, self.mode = cat, tab
        if self.settings.get("last_category") != cat.title:
            self.settings["last_category"] = cat.title
            write_settings(self.settings)
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {cat.title}")
        self._draw_chrome()
        self.view = LoadsView(self, stage, cat, info["detail"] + self.hand_loads(cat),
                              info["detail_error"], snap)
        self._update_scroll()


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
            if not dia:                       # a "gauge" / "bore" name has no bullet diameter
                raise ValueError("Enter the bullet diameter.")
            if bc is None:
                bc = estimate_bc(gr, dia, cat.title == "Handgun")
            total = num("total", "Total cost", 0, blank=True)
            cost = parts_cost() if total is None else total
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


def grades_chip(app, parent, command):
    """The 'S-F grades  On / Off' switch on the Settings page (both tools; remembered)."""
    chip = tk.Label(parent, text="", font=app.f(10, True), padx=10, pady=3, cursor="hand2")
    chip.bind("<Button-1>", lambda e: command())
    style_grades_chip(app, chip)
    return chip


def style_grades_chip(app, chip):
    on = app.show_grades
    chip.config(text="On" if on else "Off", width=4,
                bg=ACCENT if on else SURFACE_2, fg=ON_ACCENT if on else TEXT)


class LoadsView:
    """Load Dictionary: every brand's load of ONE cartridge, graded against each other."""
    tab = "loads"
    OPEN_ROWS = 7                     # list rows while a load's panel is open

    def __init__(self, app, stage, cat, loads, error="", snap=None):
        self.app, self.root, self.cat = app, app.root, cat
        self.loads = loads
        self.groups = self._group(loads)
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
        # +P / +P+ check boxes: untick one to hide those loads from the list (grades don't change)
        self.press_vars = {p: tk.BooleanVar(value=True) for p in PRESSURES}
        self.press_boxes = {}
        self.weight_vars = {k: tk.StringVar(value=str(v)) for k, v in default_weights(cat).items()}
        self.weights_open = False
        self.rows = []                    # computed rows for the chosen cartridge
        self.iid_row = {}
        self.selected = None              # the Load currently shown in the detail card
        self.sort = {"col": "#", "desc": False}
        self._pending = None
        self._build_ui(stage, error)
        if hasattr(self, "tree"):
            cart = self._apply_snap(snap) if snap and self.loads else None
            for var in (self.dist_var, self.gun_var, self.filter_var, *self.weight_vars.values()):
                var.trace_add("write", self._schedule)
            self.weight_vars_note()
            if cart is None and self.cartridges:      # start on the cartridge with the most loads
                cart = max(self.cartridges, key=lambda c: len(self.groups[c]))
            if cart is not None:
                self.cart_var.set(cart)
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
        for i in (1, 2):
            top.columnconfigure(i, weight=1)
        fields = ((cat.cartridge_label, None), ("DISTANCE (YD)", self.dist_var),
                  (cat.gun_label, self.gun_var))
        for i, (text, var) in enumerate(fields):
            a.label(top, text, 9, MUTED, True).grid(row=0, column=i, sticky="w",
                                                     padx=(0 if i == 0 else 8, 0))
            if var is None:
                # the cartridge menu is a search too: type "6.5" or "mag" to narrow it down
                self.cart_combo = ttk.Combobox(top, textvariable=self.cart_var,
                                               values=self.cartridges, font=a.f(12),
                                               width=max([16] + [len(c) for c in self.cartridges]))
                self.cart_combo.grid(row=1, column=i, sticky="ew", pady=(4, 0))
                self.cart_combo.bind("<<ComboboxSelected>>", lambda e: self._on_cartridge())
                self.cart_search = LoadSearch(a, self.cart_combo, self.cartridges,
                                              lambda n: self._on_cartridge())
            else:
                ttk.Entry(top, textvariable=var, font=a.f(12), width=10).grid(
                    row=1, column=i, sticky="ew", pady=(4, 0), padx=(8, 0))
        self.chip_row = tk.Frame(card, bg=SURFACE)
        self.chip_row.grid(row=5, column=0, sticky="w", pady=(12, 0), **pad)
        self.src_row = tk.Frame(card, bg=SURFACE)
        self.src_row.grid(row=6, column=0, sticky="w", pady=(8, 16), **pad)
        self.status = a.label(card, "", 10, DANGER, anchor="w")
        self.status.grid(row=1, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_toggle = tk.Label(card, text="▸  Scoring weights", bg=SURFACE, fg=MUTED,
                                       font=a.f(10, True), cursor="hand2")
        self.weights_toggle.grid(row=2, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_toggle.bind("<Button-1>", lambda e: self._toggle_weights())
        right = tk.Frame(card, bg=SURFACE)
        right.grid(row=2, column=0, sticky="e", pady=(8, 0), **pad)
        if cat.grain_style:
            add = tk.Label(right, text="+  Add handload", bg=SURFACE, fg=ACCENT, font=a.f(10, True),
                           cursor="hand2")
            add.pack(side="left")
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
        tbl.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        tbl.columnconfigure(0, weight=1)
        # the brand / load filter sits right above the list it filters (issue #26); label over
        # the box like the fields in the card, the load count level with the box
        above = tk.Frame(tbl, bg=BG)
        above.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        above.columnconfigure(1, weight=1)
        a.label(above, "FILTER BRAND / LOAD", 9, MUTED, True, bg=BG).grid(row=0, column=0, sticky="w")
        fl = tk.Frame(above, bg=BG)
        fl.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(fl, textvariable=self.filter_var, font=a.f(10), width=28).pack(side="left")
        # +P / +P+ check boxes, only for cartridges that have such loads
        self.press_row = tk.Frame(fl, bg=BG)
        self.press_row.pack(side="left", padx=(14, 0))
        self.count_lbl = a.label(above, "Choose a cartridge to see how every brand's load compares.",
                                 10, MUTED, bg=BG, anchor="e")
        self.count_lbl.grid(row=1, column=1, sticky="e", pady=(4, 0), padx=(16, 0))
        # (for bullets the weight is already in the Load text, so no separate Grains column)
        self.cols = ["#", "Load"] + ([] if cat.grain_style else [cat.payload_col])
        if cat.grain_style:
            self.cols += ["Barrel", "Use"]
        self.cols += ["Velocity", "Energy", "Recoil"]
        if cat.terminal:
            self.cols += ["Taylor", "HITS"]
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
        self.col_widths, self.sized = {}, None     # sized = cartridge the widths were measured for
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
        self.tree.tag_configure("hand", foreground=HAND_FG)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        # ---- selected load
        self.detail = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.detail.columnconfigure(0, weight=1)
        self.d_title = a.label(self.detail, "", 16, TEXT, True, anchor="w", justify="left",
                               wraplength=a.px(820))
        self.d_title.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        close = tk.Label(self.detail, text="✕", bg=SURFACE, fg=MUTED, font=a.f(15, True),
                         padx=8, pady=2, cursor="hand2")
        close.grid(row=0, column=1, sticky="ne", padx=(0, 10), pady=(10, 0))
        close.bind("<Button-1>", lambda e: self._close_detail())
        close.bind("<Enter>", lambda e: close.config(fg=TEXT, bg=SURFACE_2))
        close.bind("<Leave>", lambda e: close.config(fg=MUTED, bg=SURFACE))
        self.d_info = a.label(self.detail, "", 12, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_info.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))
        # the four factors sit side by side, packed to the left (no stretched columns)
        factors = tk.Frame(self.detail, bg=SURFACE)
        factors.grid(row=2, column=0, sticky="w", padx=18)
        self.d_badges = {}
        for i, key in enumerate(self.keys):
            cell = tk.Frame(factors, bg=SURFACE)
            cell.pack(side="left", padx=(0, 34))
            a.label(cell, METRICS[key][0].upper(), 10, MUTED, True).pack(anchor="w")
            line = tk.Frame(cell, bg=SURFACE)
            line.pack(anchor="w", pady=(4, 0))
            val = a.label(line, "", 16, TEXT, True)
            val.pack(side="left")
            badge = tk.Label(line, text="", width=2, font=a.f(13, True))
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
        self.h2h_btn = a.button(self.detail, "", self._h2h_click)
        self.h2h_btn.grid(row=3, column=0, columnspan=2, sticky="e", padx=18, pady=(14, 0))
        a.label(priceline, "YOUR PRICE PER ROUND ($)", 9, MUTED, True).pack(side="left")
        ttk.Entry(priceline, textvariable=self.price_var, width=8, font=a.f(11)).pack(
            side="left", padx=8)
        a.button(priceline, "Set price", self._set_price, "primary").pack(side="left")
        a.button(priceline, "Use catalog estimate", self._reset_price).pack(side="left", padx=8)
        self.d_note = a.label(self.detail, "", 10, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_note.grid(row=4, column=0, sticky="w", padx=18, pady=(10, 6))
        self.bt_toggle = tk.Label(self.detail, text="", bg=SURFACE, fg=ACCENT, font=a.f(11, True),
                                  cursor="hand2")
        self.bt_toggle.grid(row=5, column=0, sticky="w", padx=18, pady=(4, 14))
        self.bt_toggle.bind("<Button-1>", lambda e: self._toggle_ballistics())
        self.bt_frame = tk.Frame(self.detail, bg=SURFACE)
        self.bt_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 16))
        self.bt_frame.grid_remove()
        self.detail.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self.detail.grid_remove()
        self.footnote = a.label(outer, "", 9, MUTED, bg=BG, anchor="w", justify="left",
                                wraplength=a.px(880))
        self.footnote.grid(row=6, column=0, sticky="w", pady=(10, 0))
        self._apply_grades()

    # ---- state ------------------------------------------------------------ #
    def snapshot(self):
        return dict(cart=self.cart_var.get(), dist=self.dist_var.get(), gun=self.gun_var.get(),
                    gun_auto=getattr(self, "_gun_auto", self.cat.default_gun_lb),
                    weights={k: v.get() for k, v in self.weight_vars.items()},
                    weights_open=self.weights_open, purpose=self.purpose, source=self.source,
                    pressure={p: v.get() for p, v in self.press_vars.items()})

    def restore(self, snap):
        if not self.loads or not hasattr(self, "tree"):
            return
        cart = self._apply_snap(snap)
        if cart is not None:
            self.cart_var.set(cart)
            self._on_cartridge()

    def _apply_snap(self, snap):
        """Put a snapshot's settings back; returns its cartridge if it is still listed."""
        self.purpose = snap.get("purpose", "All")
        self.source = snap.get("source", "All")
        for p, on in snap.get("pressure", {}).items():
            if p in self.press_vars:
                self.press_vars[p].set(bool(on))
        for k, v in snap.get("weights", {}).items():
            if k in self.weight_vars:
                self.weight_vars[k].set(v)
        if "dist" in snap:
            self.dist_var.set(snap["dist"])
        if "gun" in snap:
            self.gun_var.set(snap["gun"])
            self._gun_auto = snap.get("gun_auto", self.cat.default_gun_lb)
        if snap.get("weights_open") and not self.weights_open:
            self._toggle_weights()
        return snap.get("cart") if snap.get("cart") in self.groups else None

    # ---- helpers ---------------------------------------------------------- #
    def _toggle_weights(self):
        self.weights_open = not self.weights_open
        if self.weights_open:
            self.weights_frame.grid()
        else:
            self.weights_frame.grid_remove()
        self.weights_toggle.config(text=("▾" if self.weights_open else "▸") + "  Scoring weights")
        self.fit_table_height()

    def _apply_grades(self):
        """Show or hide the S-F grades: the rank (#) / Score / Grade columns and the factor
        badges. With grades off the list keeps its default order, just without the ranks
        (issue #4)."""
        on = self.app.show_grades
        self.tree.configure(displaycolumns=[c for c in self.cols
                                            if on or c not in ("#", "Score", "Grade")])
        # without the # column the load names would sit against the table's edge: the empty
        # tree column (#0) gives them a little room on the left instead
        # (_render takes its width back out of the Load column, so the table is no wider)
        self.tree.configure(show="headings" if on else ("tree", "headings"))
        self.tree.column("#0", width=self.app.px(6), minwidth=self.app.px(6), stretch=False)
        self.footnote.config(text=(
            f"Grades compare loads of the same cartridge with each other (the average scores "
            f"{REL_CENTER:.0f}). " if on else "") + "Prices are estimates: set your own.")

    def _h2h_click(self):
        item = self.selected
        if item is None:
            return
        picks = self.app.h2h
        if pick_key(self.cat, item) in picks or len(picks) >= H2H_MAX:
            self.app.show_h2h()
            return
        self.app.add_to_h2h(self.cat, item)
        self._style_h2h()

    def _style_h2h(self):
        picks = self.app.h2h
        n = len(picks)
        if self.selected is not None and pick_key(self.cat, self.selected) in picks:
            text = f"In Head to Head ({n} of {H2H_MAX})  ·  Open  ›"
        elif n >= H2H_MAX:
            text = f"Head to Head is full ({H2H_MAX})  ·  Open  ›"
        else:
            text = "+  Head to Head" + (f"  ({n} picked)" if n else "")
        self.h2h_btn.config(text=text)

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
        self.cart_search.last = self.cart_var.get()
        self.filter_var.set("")
        # the gun weight follows the cartridge's typical gun (GUN_LB) unless you typed your own
        new = typical_gun_lb(self.cat, self.cart_var.get())
        try:
            own = float(self.gun_var.get()) != getattr(self, "_gun_auto", self.cat.default_gun_lb)
        except ValueError:
            own = False
        if not own:
            self.gun_var.set(f"{new:g}")
        self._gun_auto = new
        if self.purpose not in self._purposes_of(self.cart_var.get()):
            self.purpose = "All"
        self._build_chips(self.cart_var.get())
        self.selected = None
        self.detail.grid_remove()
        self.refresh()

    def _group(self, loads):
        groups = group_by_cartridge(loads, True)
        if self.cat.grain_style:                    # handloads only exist for bullet categories
            groups = with_handload_only(groups, self.app.data[self.cat.title]["loads"])
        return groups

    def _reload_loads(self, select=None):
        """After adding / editing / deleting a handload: rebuild the lists and redraw."""
        info = self.app.data[self.cat.title]
        self.loads = info["detail"] + self.app.hand_loads(self.cat)
        self.groups = self._group(self.loads)
        self.cartridges = list(self.groups)
        self.cart_combo.config(values=self.cartridges,
                               width=max([16] + [len(c) for c in self.cartridges]))
        cart = select.cartridge if select else self.cart_var.get()
        if cart not in self.groups:
            cart = max(self.cartridges, key=lambda c: len(self.groups[c])) if self.cartridges else ""
        self.cart_var.set(cart)
        self.cart_search.names = self.cartridges
        self.cart_search.last = cart
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

    def _build_pressure(self, cart):
        """A check box per pressure (+P, +P+) this cartridge has loads of; unticked hides them."""
        for w in self.press_row.winfo_children():
            w.destroy()
        self.press_boxes = {}
        have = {pressure_of(x.load) for x in self.groups.get(cart, [])}
        for p in PRESSURES:
            if p not in have:
                continue
            # drawn as a box + text (ttk's clam check box is a tiny X that's hard to see)
            row = tk.Frame(self.press_row, bg=BG, cursor="hand2")
            row.pack(side="left", padx=(0, 16))
            mark = tk.Label(row, width=2, font=self.app.f(10, True), highlightthickness=1)
            mark.pack(side="left")
            text = self.app.label(row, p, 10, TEXT, True, bg=BG)
            text.pack(side="left", padx=(6, 0))
            for w in (row, mark, text):
                w.bind("<Button-1>", lambda e, pr=p: self._pick_pressure(pr))
            self.press_boxes[p] = (mark, text)
        self._style_pressure()

    def _style_pressure(self):
        for p, (mark, _) in self.press_boxes.items():
            on = self.press_vars[p].get()
            mark.config(text="✓" if on else "", bg=ACCENT if on else SURFACE_2,
                        fg=ON_ACCENT, highlightbackground=ACCENT if on else MUTED)

    def _pick_pressure(self, p=None):
        if p is not None:
            self.press_vars[p].set(not self.press_vars[p].get())
        self._style_pressure()
        self.selected = None
        self.detail.grid_remove()
        self._render()

    def _press_ok(self, item):
        p = pressure_of(item.load)
        return not p or self.press_vars[p].get()

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
        self._build_pressure(cart)
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

    def _count_chips(self):
        """Chip counts follow the brand/load filter (and the purpose chips the Show choice too);
        the +P / +P+ boxes count the filtered loads, the chips leave out the hidden ones."""
        terms = self.filter_var.get().lower().split()
        items = [x for x in self.groups.get(self.cart_var.get(), [])
                 if all(t in x.label.lower() for t in terms)]
        for p, (_, text) in self.press_boxes.items():
            text.config(text=f"{p} ({sum(pressure_of(x.load) == p for x in items)})")
        items = [x for x in items if self._press_ok(x)]
        for name, chip in self.src_chips.items():
            n = sum(name == "All" or x.handload == (name == "Handloads") for x in items)
            chip.config(text=f"{name} ({n})")
        shown = [x for x in items if self.source == "All" or x.handload == (self.source == "Handloads")]
        for name, chip in self.chips.items():
            n = len(shown) if name == "All" else sum(self._purpose_of(x) == name for x in shown)
            chip.config(text=f"{name} ({n})")

    def _style_chips(self):
        for name, chip in self.chips.items():
            on = name == self.purpose
            chip.config(bg=ACCENT if on else SURFACE_2, fg=ON_ACCENT if on else TEXT)
        for name, chip in self.src_chips.items():
            on = name == self.source
            chip.config(bg=ACCENT if on else SURFACE_2, fg=ON_ACCENT if on else TEXT)

    def _pick_purpose(self, name):
        self.purpose = name
        self.selected = None
        self.detail.grid_remove()
        self._style_chips()
        self.refresh()

    # ---- compute + render ------------------------------------------------- #
    def refresh(self):
        if self._pending is not None:                 # this redraw covers any queued one
            try:
                self.root.after_cancel(self._pending)
            except Exception:
                pass
        self._pending = None
        alive = getattr(self.tree, "winfo_exists", None)
        if alive is not None and not alive():          # a delayed refresh after leaving this tab
            return
        cart = self.cart_var.get()
        items = self.groups.get(cart)
        if items is None:
            return
        if not items:                                # a cartridge with no factory loads yet
            self.tree.delete(*self.tree.get_children())
            self.rows = []
            self.selected = None
            self.detail.grid_remove()
            self.count_lbl.config(text=f"No factory loads listed for {cart}. Use \"+ Add handload\" "
                                       "to grade your own.")
            return
        if self.purpose != "All":
            items = [x for x in items if self._purpose_of(x) == self.purpose]
        try:
            dist = self._num(self.dist_var, "Distance", 0, self.cat.max_distance)
            gun = self._num(self.gun_var, "Gun weight", 0.5, GUN_LB_MAX)
            weights = {k: self._num(v, f"{METRICS[k][0]} weight", 0, 10)
                       for k, v in self.weight_vars.items()}
        except ValueError as exc:
            self.status.config(text=str(exc))
            return
        self.status.config(text="")
        self.rows = score_loads(items, dist, gun, weights,
                                [self.app.price_for(self.cat, x) for x in items],
                                by_type=not self.cat.grain_style)
        self.group_order = {k: n for n, k in enumerate(dict.fromkeys(r["group"] for r in self.rows))}
        for r in self.rows:
            r["custom_price"] = abs(r["stats"]["cost"] - r["item"].default_cost) > 1e-9
        self.dist = dist
        self._render()

    def _sort_by(self, col):
        first = col in (self.cat.payload_col, "Velocity", "Energy", "Taylor", "HITS", "Score")
        if self.sort["col"] == col and not self.app.show_grades and self.sort["desc"] != first:
            # grades off hides the # column, so a third click on a heading goes back to the
            # default order instead
            self.sort = {"col": "#", "desc": False}
            return self._render()
        if self.sort["col"] == col:
            self.sort["desc"] = not self.sort["desc"]
        else:
            self.sort = {"col": col, "desc": first}
        if col == "#":
            self.sort["desc"] = False
        self._render()

    def _render(self):
        if not self.groups.get(self.cart_var.get()):
            return                                   # nothing to list (refresh says why)
        self._count_chips()
        terms = self.filter_var.get().lower().split()
        data = [r for r in self.rows if all(t in r["item"].label.lower() for t in terms)
                and (self.source == "All" or r["item"].handload == (self.source == "Handloads"))
                and self._press_ok(r["item"])]
        keys = {"#": lambda r: (self.group_order.get(r["group"], 0), r["rank"]), "Load": lambda r: (r["item"].label.lower(), r["stats"]["weight"]),
                self.cat.payload_col: lambda r: r["stats"]["weight"],
                "Barrel": lambda r: r["item"].barrel_in or 999,
                "Use": lambda r: (r["item"].purpose, r["rank"]),
                "Velocity": lambda r: r["stats"]["velocity"],
                "Energy": lambda r: r["stats"]["energy"],
                "Recoil": lambda r: r["stats"]["recoil"],
                "Taylor": lambda r: r["stats"]["taylor"], "HITS": lambda r: r["stats"]["hits"],
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
                vals += [f"{st['taylor']:.1f}", f"{st['hits']:.0f}"]
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
        if self.sized != self.cart_var.get():
            # new cartridge: measure the columns afresh, so a list of short names isn't left
            # as wide as the last cartridge's longest name (filtering within one keeps them)
            self.col_widths.clear()
        self.app.fit_columns(self.tree, self.cols, cells, "Load", self.col_widths)
        if not self.app.show_grades:
            # the left gap (tree column #0) comes out of the Load column's spare room
            gap = self.app.px(6)
            self.tree.column("Load", width=self.col_widths["Load"] - gap,
                             minwidth=max(0, int(self.tree.column("Load", "minwidth")) - gap))
        if self.sized != self.cart_var.get() and cells:
            # widen the window (never shrinks, stays on screen) if every column doesn't fit
            self.sized = self.cart_var.get()
            self.app.root.update_idletasks()
            self.app.grow_to_fit(sum(self.col_widths.values()) - self.tree.winfo_width())
        self.fit_table_height()

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
                "taylor": f"{st['taylor']:.1f}",
                "hits": f"{st['hits']:.0f} ({hits_class(st['hits'])})"}
        for key, (val, badge) in self.d_badges.items():
            grade = grade_relative(row["scores"][key])
            bg, fg = GRADE_COLORS[grade]
            val.config(text=vals[key])
            if self.app.show_grades:
                badge.config(text=grade, bg=bg, fg=fg)
                badge.pack(side="left", padx=(6, 0))
            else:
                badge.pack_forget()
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
        rank = (f"Overall {row['grade']}  ·  {row['overall']:.0f}  ·  Rank #{row['rank']} of "
                f"{row['peers']}{' ' + row['group'] + ' loads' if row['group'] else ''}.  "
                if self.app.show_grades else "")
        self.d_note.config(text=rank + src)
        self._style_h2h()
        self._draw_ballistics()
        self.detail.grid()
        self.fit_table_height()

    def _toggle_ballistics(self):
        self.ballistics_open = not getattr(self, "ballistics_open", False)
        self._draw_ballistics()
        self.fit_table_height()

    def _draw_ballistics(self):
        """The selected load's ballistic table, under its scores (opened with the ▸ link)."""
        a, cat, item = self.app, self.cat, self.selected
        is_open = getattr(self, "ballistics_open", False)
        self.bt_toggle.config(text=("▾" if is_open else "▸") + "  Ballistic table")
        for w in self.bt_frame.winfo_children():
            w.destroy()
        if not is_open or item is None:
            self.bt_frame.grid_remove()
            return
        heads = ["Yards", "Velocity (fps)", "Energy (ft-lbs)", "Path (in)",
                 f"Wind drift (in, {WIND_MPH:g} mph)"]
        for c, h in enumerate(heads):
            a.label(self.bt_frame, h, 10, MUTED, True, anchor="e").grid(
                row=0, column=c, sticky="e", padx=(0 if c == 0 else 26, 0), pady=(0, 4))
        for r, (yd, v, e, path, drift) in enumerate(ballistic_table(item, cat), start=1):
            for c, text in enumerate((f"{yd:g}", f"{v:,.0f}", f"{e:,.0f}", "0.0" if abs(path) < 0.05 else f"{path:+.1f}",
                                      f"{drift:.1f}")):
                a.label(self.bt_frame, text, 11, TEXT, c == 0, anchor="e").grid(
                    row=r, column=c, sticky="e", padx=(0 if c == 0 else 26, 0), pady=1)
        a.label(self.bt_frame, f"Zeroed at {cat.zero_yd:g} yd with the sight {cat.sight_in:g} in "
                f"above the bore; drop and drift are estimates from the G1 BC, sea-level air.",
                9, MUTED, anchor="w", justify="left", wraplength=a.px(760)).grid(
            row=99, column=0, columnspan=5, sticky="w", pady=(8, 0))
        self.bt_frame.grid()

    def _close_detail(self):
        """The panel's ✕: deselect the load and give the table its rows back."""
        self.selected = None
        self.detail.grid_remove()
        self.tree.selection_remove(*self.tree.selection())
        self.fit_table_height()

    def fit_table_height(self):
        """Give the table as many rows as fit in the window, so the selected load's scores
        (below the table) show without scrolling at the default window size. With nothing
        selected the table fills the window down to the footnote. Never fewer than 6 rows
        (the page scrolls instead) and never more rows than loads."""
        a = self.app
        try:
            a.root.update_idletasks()
            last = self.detail if self.selected is not None else self.footnote
            if not last.winfo_ismapped():
                return a.fit_window()
            rowh = a.px(28)
            rows_now = int(self.tree.cget("height"))
            bottom = last.winfo_rooty() + last.winfo_height() - a.stage.winfo_rooty()
            spare = a.canvas.winfo_height() - a.px(22) - (bottom - rows_now * rowh)
            n = len(self.tree.get_children())
            rows = min(max(spare // rowh, 6), max(n, 1))
            if self.selected is not None:          # the selected load gets the room, not the list
                rows = min(rows, self.OPEN_ROWS)
        except tk.TclError:
            return
        if rows != rows_now:
            self.tree.configure(height=rows)
        a.fit_window()
        sel = self.tree.selection()
        if sel:
            self.tree.see(sel[0])
            a.root.update_idletasks()
            # keep the scores panel in view if the page still has to scroll
            bottom = last.winfo_rooty() + last.winfo_height() - a.stage.winfo_rooty()
            page, view = a.stage.winfo_reqheight(), a.canvas.winfo_height()
            if page > view:
                a.canvas.yview_moveto(max(0.0, (bottom - view + a.px(22)) / page))

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


class LoadSearch:
    """Type into a load or cartridge menu to search it (issue #24; cartridges too since Oct
    2026). The matches show in a list under the box while the box keeps the keyboard: every
    typed word must appear in the name (brand, bullet, weight...), Up/Down move, Enter or a
    click picks, Esc closes.
    names: the searched list. value(name): the box text once a name is picked (default: the
    name). valid: the box texts that count as a pick; browse: what Down lists with nothing typed
    (both default to names). on_pick(name) gets the picked name from the list."""
    MAX_ROWS = 12

    def __init__(self, app, box, names, on_pick, value=None):
        self.app, self.box, self.names, self.on_pick = app, box, names, on_pick
        self.value = value or (lambda n: n)
        self.valid = self.browse = None   # None: the same as names
        self.var = box.cget("textvariable")
        self.popup = self.listbox = None
        self.matches = []
        self.last = ""                    # the pick before the typing started
        box.bind("<KeyRelease>", self._typed)
        box.bind("<Down>", lambda e: self._move(1))
        box.bind("<Up>", lambda e: self._move(-1))
        box.bind("<Return>", lambda e: self._pick())
        box.bind("<Escape>", lambda e: self.close())
        box.bind("<FocusIn>", lambda e: box.select_range(0, "end"))
        box.bind("<FocusOut>", lambda e: box.after(150, self._left))

    def text(self):
        return self.box.getvar(self.var)

    def _typed(self, e):
        if e.keysym in ("Down", "Up", "Return", "KP_Enter", "Escape", "Tab", "ISO_Left_Tab"):
            return
        if self._ok(self.text()):
            self.close()
            return
        self.matches = self._find(self.text())
        self._show()

    def _ok(self, text):
        return text in (self.names if self.valid is None else self.valid)

    def _find(self, text):
        words = text.lower().split()
        return [n for n in self.names if all(w in n.lower() for w in words)]

    def _show(self):
        if not self.matches:
            self.close()
            return
        a = self.app
        if self.popup is None:
            self.popup = tk.Toplevel(self.box)
            self.popup.wm_overrideredirect(True)
            self.listbox = tk.Listbox(self.popup, bg=SURFACE_2, fg=TEXT, selectbackground=ACCENT,
                                      selectforeground=ON_ACCENT, font=a.f(11), activestyle="none",
                                      highlightthickness=1, highlightbackground=BORDER,
                                      borderwidth=0, takefocus=0, exportselection=False)
            self.listbox.pack(fill="both", expand=True)
            self.listbox.bind("<ButtonRelease-1>", lambda e: self._pick(self.listbox.nearest(e.y)))
            a.search_popup = self
        self.listbox.delete(0, "end")
        for n in self.matches:
            self.listbox.insert("end", n)
        self.listbox.config(height=min(len(self.matches), self.MAX_ROWS))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(0)
        self.popup.wm_geometry(f"+{self.box.winfo_rootx()}+{self.box.winfo_rooty() + self.box.winfo_height()}")
        self.popup.update_idletasks()
        self.popup.wm_geometry(f"{max(self.box.winfo_width(), self.listbox.winfo_reqwidth())}x"
                               f"{self.listbox.winfo_reqheight()}")
        self.popup.lift()

    def _move(self, step):
        if self.popup is None:
            self.matches = list(self.names if self.browse is None else self.browse) \
                if self._ok(self.text()) or not self.text().strip() else self._find(self.text())
            self._show()
            return "break"
        cur = self.listbox.curselection()
        i = min(max((cur[0] if cur else -1) + step, 0), len(self.matches) - 1)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(i)
        self.listbox.see(i)
        return "break"

    def _typed_pick(self):
        """The name whose box text was typed out in full instead of picked from the list (the
        list closes then), or None if the text is no pick or the one already made."""
        text = self.text()
        if text == self.last or not self._ok(text):
            return None
        return next((n for n in (self.names if self.browse is None else self.browse)
                     if self.value(n) == text), None)

    def _pick(self, i=None):
        if self.popup is None:                # a name typed out in full + Enter picks it too
            name = self._typed_pick()
            if name is not None:
                self.on_pick(name)
        elif self.matches:
            if i is None:
                cur = self.listbox.curselection()
                i = cur[0] if cur else 0
            name = self.matches[i]
            self.box.setvar(self.var, self.value(name))
            self.close()
            self.box.focus_set()
            self.box.icursor("end")
            self.on_pick(name)
        return "break"

    def _left(self):
        """Focus left the box: drop typing that isn't a pick (the pick before it stays)."""
        try:
            if not self.box.winfo_exists():
                return
            focus = self.box.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        if focus is self.box or (focus is not None and focus is self.listbox):
            return
        self.close()
        if not self._ok(self.text()):
            self.box.setvar(self.var, self.last if self._ok(self.last) else "")
            return
        name = self._typed_pick()             # typed out in full: the table follows the box
        if name is not None:
            self.on_pick(name)

    def close(self):
        if self.popup is not None:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = self.listbox = None
        if getattr(self.app, "search_popup", None) is self:
            self.app.search_popup = None


class HeadToHeadView:
    """Head to Head: 2-5 loads side by side, from any cartridges of any category, on one page
    (no category of its own). Each load keeps the grade it has in its Load Dictionary, with that
    category's scoring weights, so the two tools always agree."""
    tab = "h2h"
    cat = None
    FACTORS = ("velocity", "energy", "recoil", "cost", "taylor", "hits")

    def __init__(self, app, stage, snap=None):
        self.app, self.root = app, app.root
        # the category last opened in the Load Dictionary: listed first, new rows start there
        first = next((c for c in CATEGORIES if c.title == app.settings.get("last_category")),
                     CATEGORIES[0])
        self.first = first
        # every category's loads: (category title, cartridge) -> loads
        self.cats, self.groups, self.cartridges = {}, {}, {}
        for c in [first] + [c for c in CATEGORIES if c is not first]:
            info = app.data.get(c.title, {})
            items = [] if info.get("error") else info.get("detail", []) + app.hand_loads(c)
            groups = {k: v for k, v in group_by_cartridge(items, True).items() if v}
            if not groups:
                continue
            self.cats[c.title] = c
            self.cartridges[c.title] = list(groups)
            for cart, v in groups.items():
                self.groups[(c.title, cart)] = v
        # the cartridge search covers every category: "6.5 Creedmoor  ·  Rifle" -> (category, cartridge)
        self.cart_names = {f"{cart}  ·  {t}": (t, cart) for t, carts in self.cartridges.items()
                           for cart in carts}
        self.choices = {}                 # (category, cartridge) -> {text in the load menu: Load}
        for key, items in self.groups.items():
            self.choices[key] = {x.label + ("  (handload)" if x.handload else ""): x for x in items}
        self.dist_var = tk.StringVar(value=f"{H2H_DISTANCE:g}")
        # gun weight per load, hidden until opened: while hidden every load is in its
        # cartridge's typical gun (GUN_LB); a blank box means the same
        self.gun_open = False
        self.slots = []                   # [{cat, cart, load, gun: StringVar, widgets...}]
        self._pending = None
        self._build_ui(stage)
        if not hasattr(self, "slot_box"):
            return
        found = {pick_key(self.cats[t], x): (self.cats[t], x)
                 for (t, _), items in self.groups.items() for x in items}
        picks = [found[k] for k in app.h2h if k in found][:H2H_MAX]
        for icat, item in picks:
            self._add_slot(item, icat)
        while len(self.slots) < H2H_MIN:
            self._add_slot()
        self._save_picks()
        if snap:
            self._apply_snap(snap)
        self.dist_var.trace_add("write", self._schedule)
        self._layout_slots()
        self.refresh()

    # ---- layout ---------------------------------------------------------- #
    def _build_ui(self, stage):
        a = self.app
        outer = tk.Frame(stage, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        outer.columnconfigure(0, weight=1)
        a.label(outer, tool_title("h2h"), 20, TEXT, True, bg=BG).grid(
            row=0, column=0, sticky="w", pady=(6, 16))
        if not self.groups:
            msg = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
            msg.grid(row=1, column=0, sticky="ew")
            a.label(msg, "No loads found.", 11, TEXT, True, anchor="w").pack(
                anchor="w", padx=18, pady=(16, 4))
            a.label(msg, "Put the loads_*.csv files next to the program to use this tab.",
                    10, MUTED, anchor="w").pack(anchor="w", padx=18, pady=(0, 16))
            return

        card = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=1, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        pad = dict(padx=18)
        a.label(card, "LOADS TO COMPARE  ·  any category  ·  type in a cartridge or load box "
                "to search", 9, MUTED, True).grid(row=0, column=0, sticky="w", pady=(16, 0), **pad)
        self.slot_box = tk.Frame(card, bg=SURFACE)
        self.slot_box.grid(row=1, column=0, sticky="ew", pady=(6, 0), **pad)
        self.slot_box.columnconfigure(3, weight=1)
        self.add_link = tk.Label(card, text=f"+  Add a load (up to {H2H_MAX})", bg=SURFACE,
                                 fg=ACCENT, font=a.f(10, True), cursor="hand2")
        self.add_link.grid(row=2, column=0, sticky="w", pady=(8, 0), **pad)
        self.add_link.bind("<Button-1>", lambda e: self._add_slot(focus=True))

        top = tk.Frame(card, bg=SURFACE)
        top.grid(row=3, column=0, sticky="ew", pady=(16, 0), **pad)
        a.label(top, "DISTANCE (YD)", 9, MUTED, True).grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.dist_var, font=a.f(12), width=10).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        # opens a gun weight box on each load's row
        self.gun_link = tk.Label(top, text="", bg=SURFACE, fg=ACCENT, font=a.f(10, True),
                                 cursor="hand2")
        self.gun_link.grid(row=1, column=1, sticky="w", padx=(24, 0), pady=(4, 0))
        self.gun_link.bind("<Button-1>", lambda e: self._toggle_gun())
        self.status = a.label(card, "", 10, DANGER, anchor="w")
        self.status.grid(row=4, column=0, sticky="w", pady=(8, 0), **pad)
        a.label(card, "", 4).grid(row=5, column=0)

        self.results = tk.Frame(outer, bg=BG)
        self.results.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.results.columnconfigure(0, weight=1)
        self.footnote = a.label(outer, "", 9, MUTED, bg=BG, anchor="w", justify="left",
                                wraplength=a.px(880))
        self.footnote.grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _add_slot(self, item=None, icat=None, focus=False):
        if len(self.slots) >= H2H_MAX:
            return
        a = self.app
        slot = {"cat": tk.StringVar(value=(icat or self.first).title),
                "cart": tk.StringVar(value=item.cartridge if item else ""),
                "load": tk.StringVar(value=""), "gun": tk.StringVar(value="")}
        if item is not None:
            slot["load"].set(next(t for t, x in self.choices[(icat.title, item.cartridge)].items()
                                  if x is item))
        elif self.slots:                          # a new row starts on the last row's cartridge
            slot["cat"].set(self.slots[-1]["cat"].get())
            slot["cart"].set(self.slots[-1]["cart"].get())
        else:
            last = self.app.carry.get(self.first.title, {}).get("cart")
            if (self.first.title, last) in self.groups:
                slot["cart"].set(last)
        widest = max([16] + [len(c) for carts in self.cartridges.values() for c in carts])
        slot["num"] = a.label(self.slot_box, "", 11, MUTED, True)
        slot["cat_box"] = ttk.Combobox(self.slot_box, textvariable=slot["cat"], values=list(self.cats),
                                       state="readonly", font=a.f(11),
                                       width=self._chars(self.cats))
        slot["cart_box"] = ttk.Combobox(self.slot_box, textvariable=slot["cart"],
                                        values=self.cartridges.get(slot["cat"].get(), []),
                                        font=a.f(11), width=widest)
        slot["cart_search"] = LoadSearch(a, slot["cart_box"], list(self.cart_names),
                                         lambda n, s=slot: self._on_cart_search(s, n),
                                         value=lambda n: self.cart_names[n][1])
        slot["load_box"] = ttk.Combobox(self.slot_box, textvariable=slot["load"], font=a.f(11), width=40)
        slot["search"] = LoadSearch(a, slot["load_box"], [], lambda n, s=slot: self._on_load(s))
        slot["gun_box"] = tk.Frame(self.slot_box, bg=SURFACE)
        ttk.Entry(slot["gun_box"], textvariable=slot["gun"], font=a.f(11), width=6).pack(side="left")
        slot["usual"] = a.label(slot["gun_box"], "", 9, MUTED)
        slot["usual"].pack(side="left", padx=(6, 0))
        slot["gun"].trace_add("write", self._schedule)
        slot["x"] = tk.Label(self.slot_box, text="✕", bg=SURFACE, fg=MUTED, font=a.f(12, True),
                             padx=10, pady=2, cursor="hand2")
        slot["cat_box"].bind("<<ComboboxSelected>>", lambda e, s=slot: self._on_cat(s))
        slot["cart_box"].bind("<<ComboboxSelected>>", lambda e, s=slot: self._on_cart(s))
        slot["load_box"].bind("<<ComboboxSelected>>", lambda e, s=slot: self._on_load(s))
        slot["x"].bind("<Button-1>", lambda e, s=slot: self._remove_slot(s))
        slot["x"].bind("<Enter>", lambda e, s=slot: s["x"].config(fg=TEXT, bg=SURFACE_2))
        slot["x"].bind("<Leave>", lambda e, s=slot: s["x"].config(fg=MUTED, bg=SURFACE))
        self.slots.append(slot)
        self._fill_loads(slot)
        self._layout_slots()
        if focus:
            slot["load_box" if slot["cart"].get() else "cart_box"].focus_set()

    def _chars(self, texts):
        """A box width in average characters (what ttk counts) that just fits the longest
        text: names are mostly narrower letters than the "0" ttk measures by."""
        f = tkfont.Font(font=self.app.f(11))
        return math.ceil(max(f.measure(t) for t in texts) / f.measure("0")) + 1

    def _fill_loads(self, slot):
        # the cartridge search: any category's cartridge can be typed; with nothing typed,
        # Down lists this row's category
        t = slot["cat"].get()
        cs = slot["cart_search"]
        cs.valid = self.cartridges.get(t, [])
        cs.browse = [n for n, (ct, _) in self.cart_names.items() if ct == t]
        cs.last = slot["cart"].get()
        names = list(self.choices.get((slot["cat"].get(), slot["cart"].get()), {}))
        slot["load_box"].config(values=names, width=max([40] + [min(len(n), 64) for n in names]))
        slot["search"].names = names
        if slot["load"].get() not in names:
            slot["load"].set("")
        slot["search"].last = slot["load"].get()

    def _on_load(self, slot):
        """A load was picked from the menu or from the search list."""
        slot["search"].last = slot["load"].get()
        self._layout_slots()
        self._changed()

    def _layout_slots(self):
        if not hasattr(self, "gun_head"):
            self.gun_head = self.app.label(self.slot_box, "GUN WEIGHT (LB)", 9, MUTED, True)
        if self.gun_open:
            self.gun_head.grid(row=0, column=4, sticky="w", padx=(12, 0))
        else:
            self.gun_head.grid_remove()
        self.gun_link.config(text=("▾  Hide gun weights  (blank: the cartridge's usual gun)"
                                   if self.gun_open else "▸  Gun weight for each load"))
        for n, slot in enumerate(self.slots, start=1):
            slot["num"].config(text=f"{n}")
            slot["num"].grid(row=n, column=0, sticky="w", padx=(0, 10), pady=3)
            slot["cat_box"].grid(row=n, column=1, sticky="w", padx=(0, 8), pady=3)
            slot["cart_box"].grid(row=n, column=2, sticky="w", pady=3)
            slot["load_box"].grid(row=n, column=3, sticky="ew", padx=(8, 0), pady=3)
            if self.gun_open:
                t, cart = slot["cat"].get(), slot["cart"].get()
                slot["usual"].config(text=f"usual {typical_gun_lb(self.cats[t], cart):g}"
                                     if cart else "")
                slot["gun_box"].grid(row=n, column=4, sticky="w", padx=(12, 0), pady=3)
            else:
                slot["gun_box"].grid_remove()
            slot["x"].grid(row=n, column=5, sticky="w", padx=(4, 0), pady=3)
            if len(self.slots) <= H2H_MIN and not slot["load"].get():
                slot["x"].grid_remove()           # nothing to remove: the 2 rows always stay
        if len(self.slots) >= H2H_MAX:
            self.add_link.grid_remove()
        else:
            self.add_link.grid()

    def _on_cat(self, slot):
        """Another category: its cartridges go in the cartridge menu."""
        slot["cart_box"].config(values=self.cartridges.get(slot["cat"].get(), []))
        slot["cart"].set("")
        slot["load"].set("")
        slot["gun"].set("")
        self._fill_loads(slot)
        self._layout_slots()
        slot["cart_box"].focus_set()
        self._changed()

    def _on_cart_search(self, slot, name):
        """A cartridge was picked from the search list, maybe from another category."""
        t, cart = self.cart_names[name]
        slot["cat"].set(t)
        slot["cart_box"].config(values=self.cartridges.get(t, []))
        slot["cart"].set(cart)
        self._on_cart(slot)

    def _on_cart(self, slot):
        slot["load"].set("")
        slot["gun"].set("")                       # another cartridge: back to its usual gun
        self._fill_loads(slot)
        self._layout_slots()
        slot["load_box"].focus_set()
        self._changed()

    def _remove_slot(self, slot):
        """✕: remove the row, or with only the 2 rows left, just clear its load (issue #16)."""
        if len(self.slots) <= H2H_MIN:
            slot["load"].set("")
            self._layout_slots()
            self._changed()
            return
        slot["search"].close()
        slot["cart_search"].close()
        for key in ("num", "cat_box", "cart_box", "load_box", "gun_box", "x"):
            slot[key].destroy()
        self.slots.remove(slot)
        while len(self.slots) < H2H_MIN:
            self._add_slot()
        self._layout_slots()
        self._changed()

    def _picked_slots(self):
        """The loads chosen so far as (category, load, slot), in slot order, without repeats."""
        out = []
        for slot in self.slots:
            t = slot["cat"].get()
            item = self.choices.get((t, slot["cart"].get()), {}).get(slot["load"].get())
            if item is not None and all(item is not x for _, x, _ in out):
                out.append((self.cats[t], item, slot))
        return out

    def _picked(self):
        return [(c, x) for c, x, _ in self._picked_slots()]

    def _toggle_gun(self):
        self.gun_open = not self.gun_open
        self._layout_slots()
        self.refresh()

    def _save_picks(self):
        self.app.h2h[:] = [pick_key(c, x) for c, x in self._picked()]

    def _changed(self):
        self._save_picks()
        self.refresh()

    # ---- state ------------------------------------------------------------ #
    def snapshot(self):
        return dict(dist=self.dist_var.get(), gun_open=self.gun_open,
                    guns={pick_key(c, x): s["gun"].get() for c, x, s in self._picked_slots()})

    def restore(self, snap):
        if not hasattr(self, "slot_box"):
            return
        self._apply_snap(snap)
        self.refresh()

    def _apply_snap(self, snap):
        if "dist" in snap:
            self.dist_var.set(snap["dist"])
        self.gun_open = snap.get("gun_open", self.gun_open)
        guns = snap.get("guns", {})
        for c, x, slot in self._picked_slots():
            if pick_key(c, x) in guns:
                slot["gun"].set(guns[pick_key(c, x)])
        self._layout_slots()

    def _schedule(self, *_):
        if self._pending is not None:
            try:
                self.root.after_cancel(self._pending)
            except Exception:
                pass
        self._pending = self.root.after(250, self.refresh)

    # ---- compute + render ------------------------------------------------- #
    def refresh(self):
        self._pending = None
        if not self.results.winfo_exists():            # a delayed refresh after leaving this tab
            return
        for w in self.results.winfo_children():
            w.destroy()
        picks = self._picked_slots()
        picked = [(c, x) for c, x, _ in picks]
        try:
            far = max([c.max_distance for c, _ in picked] or [H2H_DISTANCE])
            dist = LoadsView._num(self.dist_var, "Distance", 0, far)
            # a blank box (or the boxes hidden): the load's cartridge's typical gun (GUN_LB)
            guns = [None if not self.gun_open or not s["gun"].get().strip()
                    else LoadsView._num(s["gun"], f"Gun weight for {x.label}", 0.5, GUN_LB_MAX)
                    for _, x, s in picks]
        except ValueError as exc:
            self.status.config(text=str(exc))
            return self.app.fit_window()
        self.status.config(text="")
        grades = self.app.show_grades
        self.footnote.config(text=(
            "Each grade is the load's Load Dictionary grade: against every load of its own "
            "cartridge (shotshells: and load type), with its category's scoring weights from the "
            "Load Dictionary, not against the others here. " if grades else "") +
            "The best figure in each row is highlighted; the % shows how far the others are "
            "behind it. Prices are estimates: set your own in the Load Dictionary.")
        if len(picked) < H2H_MIN:
            self.app.label(self.results, f"Pick at least {H2H_MIN} loads to put them head to head.",
                           11, MUTED, bg=BG, anchor="w").grid(row=0, column=0, sticky="w")
            return self.app.fit_window()
        rows = h2h_rows(picked, dist, guns, self.app.dict_weights, self.app.price_for, self.groups)
        self._render(rows, dist)
        self.app.fit_window()

    def _label_w(self):
        """Width of the row-name column, so the two tables' load columns line up."""
        f = tkfont.Font(font=self.app.f(10, True))
        names = ["Rank in its cartridge", "Bullet / payload"] + [
            METRICS[k][0] + " at 0000 yd" for k in ("velocity", "energy")]
        return max(f.measure(t) for t in names) + 24

    def _cell(self, parent, r, c, text, size=10, color=None, bold=False, bg=None, **kw):
        lab = self.app.label(parent, text, size, color, bold, bg=SURFACE if bg is None else bg,
                             anchor="w", justify="left", **kw)
        lab.grid(row=r, column=c, sticky="nsew", padx=(12, 12), pady=5)
        return lab

    def _render(self, rows, dist):
        a, grades = self.app, self.app.show_grades
        n = len(rows)
        cats = list({row["cat"].title: row["cat"] for row in rows}.values())
        keys = h2h_keys(cats)
        card = tk.Frame(self.results, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=0, column=0, sticky="ew")
        card.columnconfigure(0, weight=0, minsize=self._label_w())
        for c in range(1, n + 1):
            card.columnconfigure(c, weight=1, uniform="load")
        wrap = a.px(max(160, 760 // n))
        r = 0
        # names
        for c, row in enumerate(rows, start=1):
            it = row["item"]
            box = tk.Frame(card, bg=SURFACE)
            box.grid(row=r, column=c, sticky="nsew", padx=12, pady=(14, 6))
            a.label(box, it.cartridge, 9, MUTED, True, anchor="w").pack(anchor="w")
            a.label(box, it.label, 11, HAND_FG if it.handload else TEXT, True, anchor="w",
                    justify="left", wraplength=wrap).pack(anchor="w")
            if it.handload:
                a.label(box, "handload", 9, HAND_FG, anchor="w").pack(anchor="w")
        r += 1
        if grades:
            self._cell(card, r, 0, "Overall", 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                box = tk.Frame(card, bg=SURFACE)
                box.grid(row=r, column=c, sticky="w", padx=12, pady=5)
                bg, fg = GRADE_COLORS[row["grade"]]
                tk.Label(box, text=row["grade"], bg=bg, fg=fg, width=2, font=a.f(13, True)).pack(side="left")
                a.label(box, f"{row['overall']:.0f}", 12, TEXT, True).pack(side="left", padx=(8, 0))
            r += 1
        if grades:
            self._cell(card, r, 0, "Rank in its cartridge", 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                peers = f"{row['peers']} {row['group'] + ' ' if row['group'] else ''}loads"
                self._cell(card, r, c, f"#{row['rank']} of {peers}", 10, TEXT)
            r += 1
        tk.Frame(card, bg=BORDER, height=1).grid(row=r, column=0, columnspan=n + 1, sticky="ew", pady=4)
        r += 1
        # plain facts (no best / worst)
        payload = cats[0].payload_row if len({c.payload_row for c in cats}) == 1 else "Bullet / payload"
        facts = [(payload, lambda row: h2h_payload(row["cat"], row["item"]))]
        if any(c.grain_style for c in cats):
            facts.append(("Test barrel", lambda row: "—" if not row["cat"].grain_style else
                          f"{row['item'].barrel_in:g} in" if row["item"].barrel_in else "not listed"))
        facts.append(("Purpose", lambda row: row["item"].purpose or row["item"].group or "—"))
        for name, fn in facts:
            self._cell(card, r, 0, name, 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                self._cell(card, r, c, fn(row), 10, TEXT)
            r += 1
        # graded factors: best highlighted, others show how far behind; "—" where a factor
        # doesn't apply (no Taylor KO / HITS for shotshells)
        for key in keys:
            label = METRICS[key][0] + (f" at {dist:g} yd" if key in ("velocity", "energy") else "")
            self._cell(card, r, 0, label, 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                if key not in row["keys"]:
                    self._cell(card, r, c, "—", 11, MUTED)
                    continue
                box = tk.Frame(card, bg=SURFACE)
                box.grid(row=r, column=c, sticky="w", padx=12, pady=4)
                best = key in row["best"]
                a.label(box, h2h_value(key, row["stats"][key]), 11, ACCENT if best else TEXT,
                        True).pack(side="left")
                gap = "best" if best else h2h_gap(row["gap"][key])
                if key in ("velocity", "energy") and row["dist"] != dist:
                    gap += f"  at {row['dist']:g} yd"
                a.label(box, gap, 9, ACCENT if best else MUTED, best).pack(side="left", padx=(6, 0))
                if grades:
                    g = grade_relative(row["scores"][key])
                    bg, fg = GRADE_COLORS[g]
                    tk.Label(box, text=g, bg=bg, fg=fg, width=2, font=a.f(9, True)).pack(
                        side="left", padx=(8, 0))
            r += 1
        self._cell(card, r, 0, "Best in", 10, MUTED, True)
        most = max(len(row["best"]) for row in rows)
        for c, row in enumerate(rows, start=1):
            k = len(row["best"])
            self._cell(card, r, c, f"{k} of {len(row['keys'])}", 10,
                       ACCENT if k == most and k else TEXT, k == most and k > 0)
        r += 1
        a.label(card, "", 4).grid(row=r, column=0)

        # downrange
        a.label(self.results, "DOWNRANGE  ·  velocity (fps) and energy (ft-lbs)", 9, MUTED, True,
                bg=BG, anchor="w").grid(row=1, column=0, sticky="w", pady=(16, 6))
        dr = tk.Frame(self.results, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        dr.grid(row=2, column=0, sticky="ew")
        dr.columnconfigure(0, minsize=self._label_w())
        for c in range(1, n + 1):
            dr.columnconfigure(c, weight=1, uniform="load")
        self._cell(dr, 0, 0, "Yards", 9, MUTED, True)
        for c, row in enumerate(rows, start=1):
            self._cell(dr, 0, c, row["item"].label, 9, MUTED, True, wraplength=wrap)
        table = h2h_downrange([(row["cat"], row["item"]) for row in rows])
        for i, (yd, cells) in enumerate(table, start=1):
            self._cell(dr, i, 0, f"{yd:g}", 10, TEXT, True)
            top = max(cell[1] for cell in cells if cell)
            for c, cell in enumerate(cells, start=1):
                if cell is None:
                    self._cell(dr, i, c, "—", 10, MUTED)
                    continue
                v, e = cell
                best = e >= top - 1e-9
                self._cell(dr, i, c, f"{v:,.0f}  ·  {e:,.0f}", 10, ACCENT if best else TEXT, best)


def h2h_keys(cats):
    """The factors shown in Head to Head: every factor that applies to any of the loads."""
    return [k for k in METRICS if any(k in metric_keys(c) for c in cats)]


def h2h_rows(picked, dist, guns, weights_of, price_of, groups):
    """Head to Head figures for the picked (category, load) pairs. Each load is graded the way
    its Load Dictionary grades it (against every load of its cartridge, with weights_of(category)),
    at `dist` capped to its category's max. `best` is the set of factors where it leads the picked
    loads and `gap` how far behind the leader it is, in %; factors that don't apply to a load
    (`keys`) are left out. guns: a gun weight per picked load, None (or a None in the list) for
    its cartridge's typical gun (GUN_LB). `groups` maps (category title, cartridge) to its loads;
    price_of(category, load)."""
    rows, done = [], {}
    for n, (icat, it) in enumerate(picked):
        gun = guns[n] if guns else None
        gun = typical_gun_lb(icat, it.cartridge) if gun is None else gun
        key = (icat.title, it.cartridge, gun)
        d = min(dist, icat.max_distance)
        if key not in done:
            items = groups[key[:2]]
            done[key] = {id(r["item"]): r for r in score_loads(
                items, d, gun,
                weights_of(icat), [price_of(icat, x) for x in items], by_type=not icat.grain_style)}
        rows.append(dict(done[key][id(it)], cat=icat, dist=d, keys=metric_keys(icat),
                         best=set(), gap={}))
    for key in h2h_keys([r["cat"] for r in rows]):
        have = [r for r in rows if key in r["keys"]]
        hi = METRICS[key][1]
        vals = [r["stats"][key] for r in have]
        lead = max(vals) if hi else min(vals)
        for r, v in zip(have, vals):
            if abs(v - lead) <= 1e-9 * max(1.0, abs(lead)):
                r["best"].add(key)
            r["gap"][key] = 0.0 if lead == 0 else 100.0 * (v - lead) / abs(lead)
    return rows


def h2h_downrange(picked):
    """[(yards, [(velocity, energy) or None per load])] in the steps of the picked categories'
    widest table (rifle 100 yd, rimfire 50, handgun and shotgun 25), out to 5 steps or its max;
    None past the load's own category's max distance."""
    base = max((c for c, _ in picked), key=lambda c: (c.step_yd, c.max_distance))
    out = []
    for n in range(6):
        yd = min(n * base.step_yd, base.max_distance)
        if out and yd == out[-1][0]:
            break
        cells = []
        for icat, it in picked:
            if yd > icat.max_distance:
                cells.append(None)
                continue
            v = velocity_at(it.muzzle_fps, it.bc_g1, yd)
            cells.append((v, energy_ftlbs(it.bullet_gr, v)))
        if any(cells):
            out.append((yd, cells))
    return out


def h2h_payload(cat, item):
    if cat.show_oz:
        return f"{item.bullet_gr:.0f} gr ({item.bullet_gr / GRAINS_PER_OZ:.2f} oz)"
    return f"{item.bullet_gr:g} gr"


def h2h_gap(gap):
    """How far behind the leader: "+45%", or "35x" once it is ten times or more."""
    times = 1 + gap / 100.0
    return f"{times:,.0f}x" if times >= 10 else f"{gap:+.0f}%"


def h2h_value(key, v):
    return {"velocity": f"{v:,.0f} fps", "energy": f"{v:,.0f} ft-lbs", "recoil": f"{v:.1f} ft-lbs",
            "cost": f"${v:.2f}", "taylor": f"{v:.1f}", "hits": f"{v:.0f} ({hits_class(v)})"}[key]


def sharp_on_windows():
    """Tell Windows this app draws at the screen's real DPI. Without it Windows renders the
    window at 100% and stretches it to the display scaling (125%, 150%...), which looks blurry.
    Must run before the first Tk window exists."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)     # Windows 8.1+: system DPI aware
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()          # Windows 7 / Vista
    except Exception:
        pass                                                   # blurry is better than not starting


def main():
    if tk is None:
        sys.exit("Tkinter is not available. On Linux, install it with your package manager "
                 "(for example: sudo apt install python3-tk).")
    sharp_on_windows()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
