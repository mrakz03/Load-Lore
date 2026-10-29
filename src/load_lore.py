#!/usr/bin/env python3
"""
In Like Flint - Load Lore (formerly Cartridge Value Calculator) - a desktop tool for comparing ammunition by
performance.

Two tools plus your handloads, over five categories (Centerfire Rifle, Handgun, Pistol
Caliber Carbine, Rimfire Rifle, Shotgun):
  Load Dictionary  every factory load (and your handloads) of one cartridge, graded
                   S-F against each other on velocity, energy, recoil, cost, Taylor KO
                   and HITS. The grades can be switched off.
  Head to Head     2-5 loads side by side, from any cartridges of any category.
  Handloads        your own reloads: add, edit, back up and restore them.

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
import contextlib
import bisect
import csv
import glob
import hashlib
import io
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
import time
import urllib.error
import urllib.request
import webbrowser
import zlib
from dataclasses import dataclass, replace

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
# Shown wherever handloads are (Handloads tab, handload form, an open handload); from LEGAL.md
HANDLOAD_NOTE = ("Not reloading data. The app DOES NOT check pressure or safety. Powder charges shown "
                 "are NOT load data. HANDLOAD FIGURES ARE ONLY WHAT YOU TYPE IN. Always confirm with "
                 "the manufacturer's data and a current load manual before shooting or reloading.")
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
    group: str = ""              # the menu entry it sits under (Handgun: a drop-down of two)
    menu: str = ""               # its name in that drop-down and on its page; "" = the title
    note: str = ""               # a line for the Load Dictionary's footnote
    barrel_in: float = 0.0       # the usual test barrel (inches): loads with none listed, and the
                                 # barrel length box's starting value; 0 = no barrel length switch


CATEGORIES = (
    Category("Centerfire Rifle", "Hunting, precision and military rounds",
             "ammo_centerfire_rifle.csv", 0, 2000, 8.0, "RIFLE WEIGHT (LB)",
             legacy_filename="ammo_data.csv",
             loads_filename="loads_centerfire_rifle.csv", barrel_in=24),
    Category("Handgun", "Pistol and revolver rounds",
             "ammo_handgun.csv", 0, 500, 2.0, "HANDGUN WEIGHT (LB)",
             loads_filename="loads_handgun.csv", step_yd=25, zero_yd=25, sight_in=0.6,
             group="Handgun", menu="Pistol / Revolver", barrel_in=4),
    # handgun cartridges fired from carbines and lever guns: published, reviewer-tested or
    # estimated (source "estimate") carbine velocities
    Category("Pistol Caliber Carbine", "Handgun rounds from carbine and lever-gun barrels",
             "ammo_pcc.csv", 0, 300, 6.5, "CARBINE WEIGHT (LB)",
             loads_filename="loads_pcc.csv", step_yd=50, zero_yd=50, sight_in=2.0,
             group="Handgun", barrel_in=16,
             note="Loads marked (est.) have no published carbine velocity: it is worked out from "
                  "the maker's handgun figure for a 16 in barrel."),
    Category("Rimfire Rifle", "Small-bore rimfire rounds",
             "ammo_rimfire_rifle.csv", 0, 500, 5.0, "RIFLE WEIGHT (LB)",
             weights=(3, 3, 1, 6, 3, 3),
             loads_filename="loads_rimfire_rifle.csv", step_yd=50, zero_yd=50, barrel_in=24),
    Category("Shotgun", "Birdshot, buckshot and slugs",
             "ammo_shotgun.csv", 0, 300, 7.5, "SHOTGUN WEIGHT (LB)",
             cartridge_label="GAUGE", payload_row="Payload",
             payload_col="Payload (gr)", grain_style=False, show_oz=True,
             terminal=False, weights=(3, 3, 1, 3, 0, 0),
             loads_filename="loads_shotgun.csv", step_yd=25, zero_yd=50, sight_in=0.6),
)


# a drop-down menu entry's own line in the category list (Handgun: Pistol / Revolver, PCC)
GROUP_BLURBS = {"Handgun": "Pistols, revolvers and pistol caliber carbines"}


# a category's short tag, after a cartridge that is in two categories ("9mm Luger  ·  Carbine")
CAT_TAGS = {"Centerfire Rifle": "Rifle", "Handgun": "Pistol / Revolver",
            "Pistol Caliber Carbine": "Carbine", "Rimfire Rifle": "Rimfire"}


def cat_name(cat):
    """What menus and page titles call a category ("Pistol / Revolver" for Handgun)."""
    return cat.menu or cat.title


def title_name(title):
    """cat_name for a category title."""
    return next((cat_name(c) for c in CATEGORIES if c.title == title), title)


def menu_entries():
    """The category list in order: a category on its own, or (group name, [its categories])."""
    out = []
    for cat in CATEGORIES:
        if not cat.group:
            out.append(cat)
        elif out and isinstance(out[-1], tuple) and out[-1][0] == cat.group:
            out[-1][1].append(cat)
        else:
            out.append((cat.group, [cat]))
    return out


def version_text():
    return "dev" if APP_VERSION == "dev" else f"v{APP_VERSION}"


def default_weights(cat):
    return dict(zip(METRICS, cat.weights))


def metric_keys(cat):
    """The factors that apply to a category (shotshells have no bullet diameter)."""
    return [k for k in METRICS if cat.terminal or k not in TERMINAL_KEYS]


# The tools: (key, title, blurb on the Home screen)
TOOLS = (("loads", "Load Dictionary", "Every load of a cartridge, factory or your own handload, "
                                      "graded against each other."),
         ("h2h", "Head to Head", "Put 2 to 5 loads side by side, even from different cartridges "
                                 "or categories."),
         ("hand", "Handloads", "Build and save your own reloads. They're graded in the Load "
                               "Dictionary and can go head to head."))
NAV_ORDER = ("loads", "h2h", "hand")     # the PC sidebar (Zeke, Oct 25 2026): Load Dictionary first; phones keep NAVS
H2H_MIN, H2H_MAX = 2, 5
H2H_DISTANCE = 0         # Head to Head's starting distance (yd, 0 = muzzle); each load is capped at its category's max


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
    global SIDE
    t = THEMES.get(name) or THEMES[DEFAULT_THEME]
    BG, SURFACE, SURFACE_2, BORDER = t["bg"], t["surface"], t["surface_2"], t["border"]
    SIDE = t["side"]
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
    "handload": HANDLOAD_NOTE,
    "estimate": "ESTIMATE: no carbine velocity is published for this load. Its velocity is worked "
                "out from the maker's handgun figure for a 16 in carbine barrel; ballistic "
                "coefficient, powder charge and price are as in Pistol / Revolver.",
    "tested": "Carbine velocity measured by a reviewer's chronograph, not printed by the maker; "
              "ballistic coefficient and powder charge are estimated.",
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
        ".480 Ruger": 3.5, ".44 Magnum": 3.0, "4.6x30mm": 4.5},
    "Pistol Caliber Carbine": {      # lever guns run heavier than a 9mm carbine
        ".357 Magnum": 7.0, ".44 Magnum": 7.0, ".45 Colt": 7.0, ".44-40 Winchester": 7.5},
    "Shotgun": {"10 Gauge": 10.0},
}
GUN_LB_MAX = 60.0


def typical_gun_lb(cat, cartridge):
    return GUN_LB.get(cat.title, {}).get(cartridge, cat.default_gun_lb)


# Barrel length (the Load Dictionary's switch, off by default): each load's speed is moved from
# its test barrel (the category's usual one when none is listed) to the length typed, as
# v x (length / test barrel)^n. Handgun n are the fits from loads printed at both handgun and
# carbine length (the Pistol Caliber Carbine estimates); a rifle's n grows with its powder charge
# for the bullet weight (about 22 fps an inch for .308 Winchester, 30+ for magnums, near
# published barrel-cut tests); a .22 gains little. An estimate: real barrels differ.
BARREL_N = {"auto": 0.057, "revolver": 0.132, "magnum": 0.221, "rimfire": 0.07}
STANDARD_REVOLVERS = (".38 Special", ".44 Special", ".45 Colt", ".44-40 Winchester", ".32 S&W Long")
MAGNUM_REVOLVERS = (".454 Casull", ".480 Ruger")          # (and every "... Magnum")
RIMFIRE_HANDGUN = (".22 LR", ".22 WMR")
BARREL_MIN, BARREL_MAX = 1.0, 40.0


def barrel_exponent(cat, item):
    c = item.cartridge
    if cat.title == "Rimfire Rifle" or c in RIMFIRE_HANDGUN:
        return BARREL_N["rimfire"]
    if cat.group == "Handgun":
        if "Magnum" in c or c in MAGNUM_REVOLVERS:
            return BARREL_N["magnum"]
        return BARREL_N["revolver" if c in STANDARD_REVOLVERS else "auto"]
    ratio = item.powder_gr / item.bullet_gr if item.bullet_gr > 0 else 0.0
    return min(0.25, max(0.10, 0.10 + 0.25 * ratio))


def base_load(item):
    """The listed load behind an at_barrel copy (or the load itself)."""
    return getattr(item, "base", item)


def barrel_text(cat, item):
    """Head to Head's test barrel cell: "20 in", or "20 in, shown for 16 in (est.)"."""
    if not cat.grain_style:
        return "—"
    text = f"{item.barrel_in:g} in" if item.barrel_in else "not listed"
    at = getattr(item, "at_in", 0)
    return f"{text}, shown for {at:g} in (est.)" if at else text


# A load printed without its test barrel is taken to come from the barrel most of its
# cartridge's listed loads give (.300 Blackout 16 in, 5.56 NATO 20, 10mm Auto 5, .44 Magnum 6),
# else the category's: worked out from the loads files when they are read (web: in each category's
# test_barrels). Assuming 24 in for a .300 Blackout printed from a 16 in barrel read 100+ fps slow
# at 16 in (Zeke, Oct 29 2026).
TEST_BARRELS = {}       # category title -> {cartridge: inches}


def usual_test_barrels(cat, loads):
    """{cartridge: the test barrel most of its loads list}, where that differs from the
    category's and at least two loads say so (a tie keeps the category's)."""
    counts = {}
    for x in loads:
        if x.barrel_in:
            c = counts.setdefault(x.cartridge, {})
            c[x.barrel_in] = c.get(x.barrel_in, 0) + 1
    out = {}
    for cart, c in counts.items():
        best = max(c, key=lambda b: (c[b], b == cat.barrel_in))
        if best != cat.barrel_in and c[best] >= 2 and c[best] > c.get(cat.barrel_in, 0):
            out[cart] = best
    return out


def test_barrel(cat, item):
    """The barrel a load's listed figures are from: its own, else its cartridge's usual one."""
    return item.barrel_in or TEST_BARRELS.get(cat.title, {}).get(item.cartridge, cat.barrel_in)


def at_barrel(item, cat, length):
    """The load as fired from a `length` in barrel (a copy whose .base is the listed load), or
    the load itself when the length is its test barrel's or the category has no switch."""
    test = test_barrel(cat, item)
    if not cat.barrel_in or not length or abs(length - test) < 1e-9:
        return item
    new = replace(item, muzzle_fps=item.muzzle_fps * (length / test) ** barrel_exponent(cat, item))
    new.base, new.at_in = item, length
    return new


# Twist rate ("Firearm setup", blank = not checked): a twist changes no speed. It sets how fast the
# bullet spins, so whether it flies point first: Miller's stability factor Sg (Don Miller's twist
# rule, sea-level air) from the bullet's weight, diameter, length and speed. Factory boxes don't
# print bullet length, so it is estimated from the weight (lead core, or copper for lead-free
# bullets) and the bullet's shape. Below Sg 1.5 a bullet loses BC, about 3% per 0.1 (Bryan Litz,
# Berger's twist rate calculator); below 1.0 it won't fly point first at all (keyholes).
TWIST_MIN, TWIST_MAX = 2.0, 60.0
SG_STABLE, SG_MIN = 1.5, 1.0
_COPPER = re.compile(r"copper|lead[- ]?free|\bT?TSX|\bLRX|\bGMX|\bCX\b|E-Tip|Hammer|Cutting Edge|"
                     r"Lehigh|Xtreme|Monolithic|VOR-TX|\bTAC-X|Solid\b", re.I)
# long, pointed bullets: polymer tips (the tip adds length but almost no weight, so it counts for
# little in the spin), match and boat-tail bullets
_LONG = re.compile(r"tip|V-MAX|ELD|\bSST|AccuBond|NTX|Ballistic|VLD|Hybrid|Berger|TMK|Scenar|"
                   r"\bCX\b|\bGMX|\bLRX|Varmint Grenade|Precision Hunter|Long Range|"
                   r"Match|OTM|BTHP|HPBT|SMK|Gold Medal|Sierra|Boat ?tail|\bBT\b", re.I)
_BLUNT = re.compile(r"Flat|\bFN|Round ?Nose|\bRN|Wadcutter|\bWC\b|Cast|Lever|Hard Cast|Keith|"
                    r"\bLSWC|\bSWC", re.I)


def parse_twist(text):
    """Inches per turn from "1:8", "1 in 8", "8" or "1-8"; None if blank or no number."""
    nums = re.findall(r"\d+(?:\.\d+)?", str(text or ""))
    return float(nums[-1]) if nums else None


def bullet_length_in(item, cat, diameter):
    """Estimated bullet length (in): the length of a solid cylinder of the bullet's weight at its
    diameter (lead core 10.7 g/cc, copper 8.9), times a shape factor for the nose (fitted to
    published lengths: .308 168 SMK 1.215, .224 55 FMJ 0.74, 6.5 140 ELD-M 1.39)."""
    name = item.load or ""
    dens = 8.9 if _COPPER.search(name) else 10.7
    cyl = item.bullet_gr * 0.06479891 / dens / (math.pi / 4 * (diameter * 2.54) ** 2) / 2.54
    if _BLUNT.search(name):
        shape = 1.25
    elif _LONG.search(name):
        shape = 1.45
    else:
        shape = 1.3 if cat.group == "Handgun" else 1.4
    return cyl * shape


def stability(item, cat, twist):
    """Miller's gyroscopic stability factor for the load fired in a 1:`twist` barrel (0 if it
    can't be worked out)."""
    d = item.diameter_in or bullet_diameter(item.cartridge, item.bullet_gr)
    if not twist or d <= 0 or item.bullet_gr <= 0 or item.muzzle_fps <= 0:
        return 0.0
    t, l = twist / d, bullet_length_in(item, cat, d) / d
    return (30.0 * item.bullet_gr / (t ** 2 * d ** 3 * l * (1 + l * l))
            * (item.muzzle_fps / 2800.0) ** (1 / 3))


def stability_bc(sg):
    """BC kept at stability sg: all of it from 1.5 up, 3% less per 0.1 below (85% at 1.0)."""
    return 1.0 - 0.3 * (SG_STABLE - max(sg, SG_MIN)) if sg < SG_STABLE else 1.0


def stability_text(sg, short=False):
    """'stable', 'marginal: BC -9%' or "won't stabilise" for a stability factor."""
    loss = round(100 * (1 - stability_bc(sg)))
    if sg >= SG_MIN and not loss:
        return "stable"
    if sg >= SG_MIN:
        return f"marginal{'' if short else ':'} BC −{loss}%"
    return "won't stabilise" if short else "won't stabilise (tumbles / keyholes)"


def at_firearm(item, cat, length=0.0, twist=0.0):
    """The load from your firearm: moved to a `length` in barrel (at_barrel), then checked for a
    1:`twist` barrel (a copy with .sg, .twist, and the BC a marginal spin leaves). The load itself
    when neither is set or the category has no barrel (shotshells)."""
    new = at_barrel(item, cat, length)
    if not twist or not cat.barrel_in:
        return new
    sg = stability(new, cat, twist)
    if not sg:
        return new
    out = replace(new, bc_g1=new.bc_g1 * stability_bc(sg))
    out.base, out.at_in, out.twist, out.sg = base_load(new), getattr(new, "at_in", 0), twist, sg
    return out


def stability_cell(item):
    """Head to Head's stability cell: "1.74 in 1:12, stable", or "—" with no twist set."""
    sg = getattr(item, "sg", 0)
    return f"{sg:.2f} in 1:{item.twist:g}, {stability_text(sg)} (est.)" if sg else "—"


def stability_warn(item):
    """"⚠ won't stabilise in 1:12" for a load that won't fly point first or barely does, else ""."""
    sg = getattr(item, "sg", 0)
    if not sg or stability_text(sg) == "stable":
        return ""
    return f"⚠ {stability_text(sg, True)} in 1:{item.twist:g}"


def firearm_text(cat, gun, barrel, twist):
    """The "Firearm setup" box's summary: "Manufacturer data  ·  8 lb gun" while the barrel and
    twist are blank, else "Estimate  ·  16 in  ·  1:8 twist  ·  8 lb" (Zeke, Oct 29 2026)."""
    weight = f"{gun:g} lb" if gun else "gun weight?"
    own = ([f"{barrel:g} in barrel"] if barrel and cat.barrel_in else []) + (
        [f"1:{twist:g} twist"] if twist and cat.barrel_in else [])
    if not own:
        return f"Manufacturer data  ·  {weight} gun"
    return "  ·  ".join(["Estimate"] + own + [weight])


def firearm_note(cat):
    """What the "Firearm setup" settings change, and that the listed figures are the makers'
    (web: DATA.fire_notes)."""
    if not cat.barrel_in:
        return ("Velocity and energy are the makers' published figures. Recoil is worked out "
                "for this gun weight.")
    listed = ("Velocity and energy are each maker's published figures from its own test barrel"
              + (", except loads marked (est.): most carbine figures are our estimates from the "
                 "maker's handgun figures" if cat.title == "Pistol Caliber Carbine" else "")
              + ". Recoil is worked out for this gun weight.")
    return (listed + " Type your own barrel length or twist rate and the figures become "
            "estimates for your firearm. Twist rate changes no speed: it checks whether each "
            "bullet spins fast enough to fly point first (Miller's rule, bullet length "
            "estimated) and trims the BC of one that barely does.")


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
    "4.6x30mm": 0.183,
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


# shot sizes in inches: buckshot by number, then birdshot letters; birdshot #n is (17 - n) / 100
BUCK_IN = {"000": .36, "00": .33, "0": .32, "1": .30, "2": .27, "3": .25, "4": .24}
SHOT_LETTER_IN = {"T": .20, "BBB": .19, "BB": .18, "B": .17}


def shot_size(item):
    """(size in inches, pellet count or 0, short text) of a shotshell's largest shot, from its
    name ('2¾" 00 Buck · 9 pellets', '3" #4/5/6 · 1¼ oz'); slugs come out biggest (1.0)."""
    name = item.load or ""
    seg = next((s for s in name.split(" · ") if '"' in s), name)
    seg = re.sub(r'^[\d.¼½¾⅛⅜⅝⅞]+" ?', "", seg).replace("½", ".5")
    m = re.search(r"(\d+) pellets", name)
    pellets = int(m.group(1)) if m else 0
    if item.group == "Slug" or re.search(r"\bSlug", seg):
        return 1.0, pellets, "Slug"
    m = re.search(r"\b(000|00|0|[1-4]) Buck", seg)
    if m:
        return BUCK_IN[m.group(1)], pellets, f"{m.group(1)} Buck"
    best = (0.0, pellets, "—")
    for t in re.findall(r"\b(T|BBB|BB|B|\d+(?:\.\d+)?)\b", seg):
        d = SHOT_LETTER_IN.get(t) or (17 - float(t)) / 100
        if best[0] < d <= .21:
            best = (d, pellets, t if t in SHOT_LETTER_IN else f"#{float(t):g}")
    return best


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


# cartridges that left a category (Oct 28 2026: .357 / .44 Magnum lever-gun loads went from
# Centerfire Rifle to Pistol Caliber Carbine): saved handloads and prices follow them
MOVED_CATEGORIES = {"Centerfire Rifle|.357 Magnum": "Pistol Caliber Carbine",
                    "Centerfire Rifle|.44 Magnum": "Pistol Caliber Carbine"}


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
    cat = MOVED_CATEGORIES.get(f"{parts[0]}|{name}", parts[0])
    return ["|".join([cat, c, parts[2]]) for c in SPLIT_CARTRIDGES.get(name, (name,))]


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
            moved = MOVED_CATEGORIES.get(f"{row.get('category', '')}|{row['cartridge']}")
            if moved:
                row["category"] = moved
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
    return rgba_png(size, size, raw)


def rgba_png(w, h, raw):
    """A base64 RGBA PNG from rows of RGBA bytes, each row starting with a 0 (filter: none)."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


def _rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


# The web version's sidebar icons (24 x 24 SVG strokes), as point lists: lines and circles
# (centre, radius). Drawn smooth by icon_png, since a Tk canvas draws lines without anti-aliasing.
def _arc(cx, cy, r, a0, a1, n=10):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


ICONS = {
    "home": [[(3, 11.5), (12, 4), (21, 11.5)], [(5.5, 10), (5.5, 19.5), (18.5, 19.5), (18.5, 10)]],
    "h2h": [[(12, 3), (12, 21)], [(5, 7), (19, 7)],
            [(4, 14), (7, 7), (10, 14)] + _arc(7, 14, 3, 0, 180), 
            [(14, 14), (17, 7), (20, 14)] + _arc(17, 14, 3, 0, 180)],
    "loads": [[(5, 6), (19, 6)], [(5, 12), (19, 12)], [(5, 18), (14, 18)]],
    "hand": [[(9.5, 3), (14.5, 3), (14.5, 7.5), (16.5, 10.5), (16.5, 21), (7.5, 21), (7.5, 10.5),
              (9.5, 7.5), (9.5, 3)], [(7.5, 14), (16.5, 14)]],
    "settings": [[(4, 7), (14, 7)], [(18, 7), (20, 7)], [(4, 17), (8, 17)], [(12, 17), (20, 17)],
                 _arc(16, 7, 2, 0, 360, 16), _arc(10, 17, 2, 0, 360, 16)],
}


def icon_png(name, size, colour):
    """One of ICONS as a base64 PNG, `size` px square: round-capped 1.8 px strokes on 24 px."""
    k = size / 24.0
    segs = [((x0 * k, y0 * k), (x1 * k, y1 * k)) for line in ICONS[name]
            for (x0, y0), (x1, y1) in zip(line, line[1:])]
    half = 0.9 * k
    r, g, b = _rgb(colour)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        py = y + 0.5
        for x in range(size):
            px, d = x + 0.5, 1e9
            for (ax, ay), (bx, by) in segs:
                dx, dy = bx - ax, by - ay
                ll = dx * dx + dy * dy
                t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
                d = min(d, math.hypot(px - ax - t * dx, py - ay - t * dy))
            raw += bytes((r, g, b, int(255 * max(0.0, min(1.0, half - d + 0.5)))))
    return rgba_png(size, size, raw)


def corner_png(radius, fill, border, outside, width=1):
    """The top-left corner of a rounded box, smooth: `fill` inside a `width` px `border` line,
    `outside` around it. Rotate by drawing it with other corners (RoundBox flips the maths)."""
    out = []
    for flip in ((False, False), (True, False), (False, True), (True, True)):   # tl tr bl br
        raw = bytearray()
        for y in range(radius):
            raw.append(0)
            for x in range(radius):
                cx = radius - (radius - x - 0.5 if flip[0] else x + 0.5)
                cy = radius - (radius - y - 0.5 if flip[1] else y + 0.5)
                d = math.hypot(cx, cy)
                shape = max(0.0, min(1.0, radius - d + 0.5))
                inner = max(0.0, min(1.0, radius - width - d + 0.5))
                px = [o * (1 - shape) + bd * (shape - inner) + f * inner
                      for o, bd, f in zip(_rgb(outside), _rgb(border), _rgb(fill))]
                raw += bytes([int(round(v)) for v in px] + [255])
        out.append(rgba_png(radius, radius, raw))
    return out


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


def handload_csv_text(rows):
    """Handloads as CSV text, the my_handloads.csv format (the Handloads tab's back up)."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=HANDLOAD_FIELDS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


HANDLOAD_NUMBERS = ("bullet_gr", "diameter_in", "bc_g1", "powder_gr", "muzzle_fps", "barrel_in", "cost",
                    "bullet_cost", "powder_cost_lb", "primer_cost", "brass_cost", "brass_reuse")


def merge_handload_rows(rows, text, categories):
    """Restore a back up (CSV text, my_handloads.csv or the phone's) into `rows`: a handload with
    the same id is replaced, a new one added. Rows that aren't for one of `categories` (titles)
    or lack a figure are skipped. Returns (rows, added, replaced, skipped); raises ValueError if
    the text isn't a handload back up. Same rules as mergeHand in the web version."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    head = [(k or "").strip().lower() for k in (reader.fieldnames or [])]
    if not all(k in head for k in ("cartridge", "bullet_gr", "muzzle_fps")):
        raise ValueError("That isn't a handload back up (no cartridge / bullet_gr / muzzle_fps "
                         "columns).")
    out, added, replaced, skipped = [dict(r) for r in rows], 0, 0, 0
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        row["cartridge"] = canonical_name(row.get("cartridge", ""))
        row["category"] = MOVED_CATEGORIES.get(f"{row.get('category', '')}|{row['cartridge']}",
                                               row.get("category", ""))
        try:
            ok = (row.get("category") in categories and row["cartridge"] and
                  all(float(row.get(k) or 0) > 0 for k in ("bullet_gr", "muzzle_fps", "bc_g1",
                                                            "powder_gr", "cost")))
        except ValueError:
            ok = False
        if not ok:
            skipped += 1
            continue
        for k in HANDLOAD_NUMBERS:                    # "0" from the phone means blank
            try:
                if float(row.get(k) or 0) == 0:
                    row[k] = ""
            except ValueError:
                row[k] = ""
        row["brass_reuse"] = row.get("brass_reuse") or "5"
        row["id"] = row.get("id") or new_handload_id()
        for i, r in enumerate(out):
            if r.get("id") == row["id"]:
                out[i] = row
                replaced += 1
                break
        else:
            out.append(row)
            added += 1
    return out, added, replaced, skipped


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
_CORNERS = {}           # (radius, fill, border, outside) -> four PhotoImages, shared by every box


class RoundBox(tk.Frame if tk else object):
    """A box with rounded corners like the web version's cards, chips and fields: a canvas
    behind `body` (a Frame to fill) draws the rounded outline, with smooth corners from
    corner_png. The box is as big as `body` needs plus the padding, or whatever the layout
    stretches it to. Keep some padding: `body` is square and would cover the corners.
    recolour() repaints it (hover, selected, focus)."""

    def __init__(self, parent, app, fill, border=None, outside=None, radius=12, padx=0, pady=0,
                 cursor=""):
        outside = outside if outside is not None else parent.cget("bg")
        super().__init__(parent, bg=outside, cursor=cursor)
        self.app, self.r = app, max(2, app.px(radius))
        self.fill, self.border, self.outside = fill, border or fill, outside
        self.canvas = tk.Canvas(self, bg=outside, highlightthickness=0, bd=0, cursor=cursor,
                                width=1, height=1)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)      # under body: made first
        self.body = tk.Frame(self, bg=fill, cursor=cursor)
        self.body.pack(fill="both", expand=True, padx=app.px(padx), pady=app.px(pady))
        self.canvas.bind("<Configure>", lambda e: self._draw(e.width, e.height))

    def _draw(self, w=None, h=None):
        c = self.canvas
        w = w or c.winfo_width()
        h = h or c.winfo_height()
        c.delete("box")
        r = min(self.r, w // 2, h // 2)
        if r < 2:
            return
        key = (r, self.fill, self.border, self.outside)
        if key not in _CORNERS:
            _CORNERS[key] = [tk.PhotoImage(data=d) for d in
                             corner_png(r, self.fill, self.border, self.outside)]
        tl, tr, bl, br = _CORNERS[key]
        f, b = self.fill, self.border
        c.create_rectangle(r, 0, w - r, h, fill=f, outline="", tags="box")
        c.create_rectangle(0, r, w, h - r, fill=f, outline="", tags="box")
        for x0, y0, x1, y1 in ((r, 0, w - r, 1), (r, h - 1, w - r, h), (0, r, 1, h - r),
                               (w - 1, r, w, h - r)):
            c.create_rectangle(x0, y0, x1, y1, fill=b, outline="", tags="box")
        for img, x, y in ((tl, 0, 0), (tr, w - r, 0), (bl, 0, h - r), (br, w - r, h - r)):
            c.create_image(x, y, image=img, anchor="nw", tags="box")

    def recolour(self, fill=None, border=None, widgets=()):
        """New fill / outline colours; `widgets` inside the box take the new fill as background."""
        if fill is not None:
            self.fill = fill
            for w in (self.body, *widgets):
                w.configure(bg=fill)
        if border is not None:
            self.border = border
        self._draw()

    def on_click(self, command, widgets=()):
        for w in (self, self.canvas, self.body, *widgets):
            w.bind("<Button-1>", lambda e: command())


class Pill(RoundBox):
    """A rounded button / chip with one line of text (the web's .btn, .chips button, .tgl)."""

    def __init__(self, parent, app, text, command, kind="secondary", size=11, padx=16, pady=8,
                 radius=8, outside=None, note=None):
        self.kind, self.enabled = kind, True
        bg, fg, _ = self._colours(kind)
        super().__init__(parent, app, bg, bg, outside=outside, radius=radius, padx=padx,
                         pady=pady, cursor="hand2")
        # the padding is the box's, not the label's: a label would cover the rounded corners
        self.text = tk.Label(self.body, text=text, bg=bg, fg=fg, font=app.f(size, True),
                             cursor="hand2", padx=0, pady=0)
        self.text.pack(side="left")
        # a chip's count, smaller, after its name ("Hunting 3" like the web)
        self.note = tk.Label(self.body, text=note or "", bg=bg, fg=fg, font=app.f(size - 2, True),
                             cursor="hand2", padx=0, pady=0)
        if note is not None:
            self.note.pack(side="left", padx=(app.px(4), 0), pady=(app.px(1), 0))
        self.command = command
        if kind == "chip":
            self.recolour(border=BORDER)
        for w in (self, self.canvas, self.body, self.text, self.note):
            w.bind("<Button-1>", lambda e: self.enabled and self.command and self.command())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    @staticmethod
    def _colours(kind):
        if kind == "primary" or kind == "on":
            return ACCENT, ON_ACCENT, ACCENT_HOVER
        return SURFACE_2, TEXT, BORDER                  # chip / secondary

    def _hover(self, inside):
        if not self.enabled:
            return
        bg, _, hover = self._colours(self.kind)
        c = hover if inside else bg
        self.recolour(c, BORDER if self.kind == "chip" and not inside else c, (self.text, self.note))

    def set(self, text=None, kind=None, enabled=None, note=None):
        if text is not None:
            self.text.configure(text=text)
        if note is not None:
            self.note.configure(text=note)
        if enabled is not None:
            self.enabled = enabled
            cur = "hand2" if enabled else ""
            for w in (self, self.canvas, self.body, self.text, self.note):
                w.configure(cursor=cur)
        if kind is not None:
            self.kind = kind
        bg, fg, _ = self._colours(self.kind)
        self.text.configure(fg=fg if self.enabled else MUTED)
        self.note.configure(fg=fg if self.enabled else MUTED)
        self.recolour(bg, BORDER if self.kind == "chip" else bg, (self.text, self.note))

    def config(self, **kw):            # tk.Button-style text= / state= for older callers
        if "text" in kw or "state" in kw:
            self.set(text=kw.pop("text", None),
                     enabled=None if "state" not in kw else kw.pop("state") != "disabled")
        kw.pop("cursor", None)
        if kw:
            super().configure(**kw)
    configure = config


class Badge(RoundBox):
    """An S-F grade in a small rounded box (the web's .badge)."""

    def __init__(self, parent, app, grade="", size=10):
        super().__init__(parent, app, SURFACE, outside=parent.cget("bg"), radius=6, padx=4, pady=1)
        self.text = tk.Label(self.body, width=2, font=app.f(size, True), bd=0, padx=0, pady=0)
        self.text.pack()
        if grade:
            self.set(grade)

    def set(self, grade):
        bg, fg = GRADE_COLORS[grade]
        self.text.configure(text=grade, fg=fg)
        self.recolour(bg, bg, (self.text,))


class App:
    """Owns the window, the theme, and switching between the picker and calculators."""

    WIN_W, WIN_H = 1360, 860      # default window size (clamped to small screens); resizable
    MIN_W, MIN_H = 980, 600
    SIDEBAR_W = 240

    def __init__(self, root):
        self.root = root
        # ttk selects a combobox's whole text after a pick from its drop-down; leave it plain
        # (class binding: runs after each box's own <<ComboboxSelected>>)
        root.bind_class("TCombobox", "<<ComboboxSelected>>",
                        lambda e: e.widget.selection_clear(), add="+")
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
        self.mode = "home"                # home / loads / h2h / hand / settings
        self.cat = None
        self.carry = {}                   # per category: what each tab knew when you left it
        self.open_groups = set()          # drop-down menu entries (Handgun) opened by a click
        self.h2h = []                     # the Head to Head picks (pick_key), any category
        self.h2h_snap = {}                # what Head to Head had on screen when you left it
        self._place_window()
        self._build_shell()
        self.show_launcher()
        root.bind_all("<Control-Key-1>", lambda e: self.show_picker("loads"))
        root.bind_all("<Control-Key-2>", lambda e: self.show_h2h())
        root.bind_all("<Control-Key-3>", lambda e: self.show_hand())
        root.bind_all("<Control-Key-0>", lambda e: self.show_launcher())
        # the search pop-up is drawn inside its box's window: close it when that window moves,
        # resizes or is minimised, like a menu
        for cls in ("Tk", "Toplevel"):
            for seq in ("<Configure>", "<Unmap>"):
                root.bind_class(cls, seq, self._window_moved, add="+")
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
                    TEST_BARRELS[cat.title] = usual_test_barrels(cat, detail)
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
        return self.settings.get("show_grades", False) is True

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
        # inside a rounded App.field box, which draws the outline
        flat = dict(field, bordercolor=SURFACE_2, padding=(4, 5))
        for name in ("TCombobox", "TEntry", "TSpinbox"):
            s.configure("Flat." + name, **flat)
            s.map("Flat." + name, bordercolor=[("focus", SURFACE_2)],
                  lightcolor=[("focus", SURFACE_2)], darkcolor=[("focus", SURFACE_2)],
                  fieldbackground=[("readonly", SURFACE_2)], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", SURFACE_2)], selectforeground=[("readonly", TEXT)],
                  arrowcolor=[("active", TEXT)])
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE, borderwidth=0,
                    rowheight=self.px(30), font=self.f(10))
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])   # the box draws the edge
        s.configure("Treeview.Heading", background=SURFACE_2, foreground=MUTED, borderwidth=0,
                    bordercolor=SURFACE_2, lightcolor=SURFACE_2, darkcolor=SURFACE_2,
                    relief="flat", font=self.f(9, True), padding=(6, 7))
        # thin flat scroll bars in the theme's colours
        for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            s.configure(name, background=BORDER, troughcolor=SURFACE, bordercolor=SURFACE,
                        lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED, relief="flat",
                        gripcount=0, arrowsize=self.px(12))
            s.map(name, background=[("active", MUTED)], lightcolor=[("active", MUTED)],
                  darkcolor=[("active", MUTED)])
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", ON_ACCENT)])
        # a thin line under each row, like the web's table rows: the row background is an image
        # (fill + a 1 px BORDER line at the bottom) stretched to the row, accent when selected
        def row_png(fill):
            img = tk.PhotoImage(width=3, height=3)
            img.put(fill, to=(0, 0, 3, 2))
            img.put(BORDER, to=(0, 2, 3, 3))
            return img
        self._row_imgs = (row_png(SURFACE), row_png(ACCENT))
        name = f"Rowline{len(getattr(self, '_row_names', ()))}.row"     # one element per theme
        self._row_names = getattr(self, "_row_names", ()) + (name,)
        s.element_create(name, "image", self._row_imgs[0], ("selected", self._row_imgs[1]),
                         border=(1, 0, 1, 1), sticky="nswe")
        s.layout("Treeview.Row", [(name, {"sticky": "nswe"})])
        s.map("Treeview.Heading", background=[("active", BORDER)])

    def rule(self, parent, row, span, column=0):
        """A thin line along the bottom of a grid row, like the web's table row borders
        (drawn over the row's padding, so it doesn't change the row's height)."""
        line = tk.Frame(parent, bg=BORDER, height=1)
        line.grid(row=row, column=column, columnspan=span, sticky="sew")
        line.lift()
        return line

    def label(self, parent, text="", size=11, color=None, bold=False, bg=None, **kw):
        return tk.Label(parent, text=text, bg=SURFACE if bg is None else bg,
                        fg=TEXT if color is None else color, font=self.f(size, bold), **kw)

    def button(self, parent, text, command, kind="secondary", size=11, padx=16, pady=8):
        """A rounded button like the web's .btn (primary = accent)."""
        return Pill(parent, self, text, command, kind, size=size, padx=padx, pady=pady)

    def chip(self, parent, text, command, on=False, note=None):
        """A pill-shaped filter chip like the web's .chips buttons; `note` is its count."""
        return Pill(parent, self, text, command, "on" if on else "chip", size=10, padx=13, pady=7,
                    radius=99, note=note)

    def card(self, parent, fill=None, border=None, radius=12, padx=0, pady=0, outside=None):
        """A rounded card like the web's .card / .lc: draw into its .body."""
        return RoundBox(parent, self, SURFACE if fill is None else fill,
                        BORDER if border is None else border, outside=outside, radius=radius,
                        padx=padx, pady=pady)

    def field(self, parent, widget, *args, **kw):
        """An entry or drop-down in a rounded box like the web's inputs: the box outline turns
        the accent colour while it has the focus. Returns (box, widget)."""
        box = RoundBox(parent, self, SURFACE_2, BORDER, radius=8, padx=4, pady=3)
        w = widget(box.body, *args, style="Flat.T" + widget.__name__, **kw)
        w.pack(fill="both", expand=True)
        w.bind("<FocusIn>", lambda e: box.recolour(border=ACCENT), add="+")
        w.bind("<FocusOut>", lambda e: box.recolour(border=BORDER), add="+")
        box.widget = w
        return box, w

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

        self.sidebar = tk.Frame(self.shell, bg=SIDE, width=self._sidebar_width())
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Frame(self.shell, bg=BORDER, width=1).pack(side="left", fill="y")
        self.foot = tk.Frame(self.sidebar, bg=SIDE)        # Settings, at the bottom left
        self.foot.pack(side="bottom", fill="x", padx=self.px(14), pady=(0, self.px(22)))
        self.nav = tk.Frame(self.sidebar, bg=SIDE)
        self.nav.pack(fill="x", padx=self.px(14), pady=(self.px(22), 0))

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
                                                   self._update_scroll(), self._refit_soon(),
                                                   self._menu_resized()))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._on_wheel)
            # Tk's dropdowns step their value on every wheel tick, and each step re-ran the
            # theme or cartridge change (issue #14): over a closed dropdown the wheel scrolls the page
            self.root.bind_class("TCombobox", seq, lambda e: (self._on_wheel(e), "break")[1])
        self._draw_chrome()

    def _sidebar_width(self):
        """Wide enough for the longest menu entry at the current text size and screen DPI
        (240 px like the web's sidebar at normal size)."""
        main, sub = tkfont.Font(font=self.f(11, True)), tkfont.Font(font=self.f(10, True))
        title, ver = tkfont.Font(font=self.f(15, True)), tkfont.Font(font=self.f(8))
        icon = self.px(22) + self.px(12)
        need = max([main.measure(t) + icon for _, t, _ in TOOLS] + [title.measure("Load Lore")]
                   + [ver.measure(version_text())]
                   + [sub.measure(cat_name(cat)) + self.px(24 + 9 + 10 + (12 if cat.group else 0))
                      for cat in CATEGORIES])
        return max(self.px(self.SIDEBAR_W), need + 2 * self.px(14) + 2 * self.px(12) + 4)

    def _window_moved(self, e):
        pop = getattr(self, "search_popup", None)
        if pop is None or pop.popup is None:
            return
        try:
            top = pop.box.winfo_toplevel()
            if str(e.widget) != str(top):
                return
            if str(e.type) == "Unmap" or pop.window_at() != pop.opened_at:
                pop.close()
        except tk.TclError:
            pop.close()

    def _on_wheel(self, e):
        """Scroll the page with the mouse wheel (tables and lists keep their own wheel)."""
        pop = getattr(self, "search_popup", None)
        if pop is not None:
            if pop.popup is not None and str(e.widget).startswith(str(pop.popup)):
                pop.scroll(-1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1)
                return
            pop.close()                       # the search pop-up would stay put as the page moved
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

    def icon(self, name, colour, size=22):
        """A sidebar / home-card icon (ICONS) as a PhotoImage, drawn once per colour and size."""
        key = (name, colour, self.px(size))
        cache = self.__dict__.setdefault("_icons_img", {})
        if key not in cache:
            cache[key] = tk.PhotoImage(data=icon_png(name, self.px(size), colour))
        return cache[key]

    def _nav_button(self, text, command, active, sub=False, parent=None, icon=None, indent=0):
        """A sidebar entry like the web's: icon + bold name, rounded accent fill when it's the
        open page; category entries sit indented behind a thin line, the open one grey-filled
        (a sub-category, Pistol Caliber Carbine, `indent` px further in)."""
        parent = parent or self.nav
        if sub:
            bg, fg, hover = (SURFACE_2, TEXT, SURFACE_2) if active else (SIDE, MUTED, SURFACE)
        else:
            bg, fg, hover = (ACCENT, ON_ACCENT, ACCENT) if active else (SIDE, MUTED, SURFACE)
        box = RoundBox(parent, self, bg, bg, outside=SIDE, radius=8 if sub else 10,
                       padx=10 if sub else 12, pady=6 if sub else 9, cursor="hand2")
        box.pack(fill="x", pady=(0, self.px(2 if sub else 4)), padx=(indent, 0))
        parts = []
        if icon:
            i = tk.Label(box.body, image=self.icon(icon, fg), bg=bg, cursor="hand2")
            i.pack(side="left", padx=(0, self.px(12)))
            parts.append(i)
        t = tk.Label(box.body, text=text, bg=bg, fg=fg, cursor="hand2", anchor="w",
                     font=self.f(10 if sub else 11, active or not sub))
        t.pack(side="left", fill="x", expand=True)
        parts.append(t)
        box.on_click(command, parts)
        for w in (box, box.canvas, box.body, *parts):
            w.bind("<Enter>", lambda e: box.recolour(hover, hover, parts))
            w.bind("<Leave>", lambda e: box.recolour(bg, bg, parts))
        return box

    def _draw_chrome(self):
        """(Re)draw the sidebar: Home, the two features, and the categories of the open feature."""
        for w in self.nav.winfo_children() + self.foot.winfo_children():
            w.destroy()
        brand = tk.Frame(self.nav, bg=SIDE)
        brand.pack(fill="x", padx=self.px(6), pady=(0, self.px(18)))
        self.label(brand, "In Like Flint", 8, MUTED, True, bg=SIDE, anchor="w").pack(anchor="w")
        self.label(brand, "Load Lore", 15, TEXT, True, bg=SIDE, anchor="w").pack(anchor="w")
        self.label(brand, version_text(), 8, MUTED, bg=SIDE, anchor="w").pack(anchor="w", pady=(1, 0))
        self._nav_button("Settings", self.show_settings, self.mode == "settings",
                         parent=self.foot, icon="settings")
        self._nav_button("Home", self.show_launcher, self.mode == "home", icon="home")
        for key in NAV_ORDER:
            text = tool_title(key)
            if key in ("h2h", "hand"):        # one page for every category: no category list
                self._nav_button(text, self.show_h2h if key == "h2h" else self.show_hand,
                                 self.mode == key, icon=key)
                continue
            self._nav_button(text, lambda k=key: self.show_picker(k), self.mode == key, icon=key)
            if self.mode == key:
                # the web's sub-list: indented, a thin line down its left side
                subs = tk.Frame(self.nav, bg=SIDE)
                subs.pack(fill="x", padx=(self.px(24), 0), pady=(0, self.px(8)))
                tk.Frame(subs, bg=BORDER, width=1).pack(side="left", fill="y")
                inner = tk.Frame(subs, bg=SIDE)
                inner.pack(side="left", fill="x", expand=True, padx=(self.px(8), 0))
                for entry in menu_entries():
                    if isinstance(entry, tuple):          # Handgun: opens its two categories
                        name, cats = entry
                        here = self.cat is not None and self.cat in cats
                        shown = here or name in self.open_groups
                        self._nav_button(f"{name}  {'▾' if shown else '▸'}",
                                         lambda n=name: self._toggle_group(n), False, sub=True,
                                         parent=inner)
                        kids = cats if shown else []
                    else:
                        kids = [entry]
                    for cat in kids:
                        on = self.cat is not None and cat.title == self.cat.title
                        self._nav_button(cat_name(cat), lambda c=cat, k=key: self.go(c, k), on,
                                         sub=True, parent=inner,
                                         indent=self.px(12) if cat.group else 0)

    def _toggle_group(self, name):
        """Open or close a drop-down entry (Handgun) in the sidebar and the category list."""
        self.open_groups ^= {name}
        if self.mode in ("loads",) and self.cat is None:
            self.show_picker(self.mode)
        else:
            self._draw_chrome()

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

    # ---- Home, category list and Settings: sized to the window ------------ #
    # Each page has a size it is drawn for at zoom 1 (MENU_PAGES: content width, height). A bigger
    # window zooms the whole page up to MENU_ZOOM_MAX (text, cards, icons: App.scale is raised
    # while it is built); it stays in the top left with its cards in one column (Zeke, Oct 25
    # 2026). Resizing re-lays it out (_menu_resized).
    MENU_PAGES = {"home": (560, 460), "picker": (560, 650), "settings": (680, 680)}
    MENU_ZOOM_MAX = 1.15
    MENU_SIDE = 34                      # the page's side margin at zoom 1

    def _menu_page(self):
        if self.mode in ("home", "settings"):
            return self.mode
        if self.mode == "loads" and self.cat is None and self.view is None:
            return "picker"
        return None

    def _menu_layout(self, page):
        """(zoom, column width) for `page` in the window's current page area."""
        self.root.update_idletasks()
        box = self.canvas.master
        w = box.winfo_width() - self.vbar.winfo_reqwidth()     # the same with or without the bar
        h = box.winfo_height()
        if w <= 1 or h <= 1:                                   # not drawn yet
            w = self.root.winfo_width() - self.sidebar.winfo_reqwidth() - 1
            h = self.root.winfo_height()
        dw, dh = self.MENU_PAGES[page]
        side = 2 * self.px(self.MENU_SIDE)
        k = min((w - side) / self.px(dw), (h - self.px(54)) / self.px(dh), self.MENU_ZOOM_MAX)
        k = max(1.0, math.floor(k * 20) / 20)                  # steps of 5%
        width = max(self.px(260), min(w - side, round(self.px(dw) * k)))
        return k, width

    @contextlib.contextmanager
    def _zoomed(self, k):
        """Build with every px() / f() / icon k times bigger (the window's zoom, not the text
        size setting: that is put back when the page is built)."""
        base = self.scale
        self.scale = base * k
        try:
            yield
        finally:
            self.scale = base

    def _menu_wrap(self, stage, width):
        """The page's column in the top left, `width` wide."""
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(anchor="nw", padx=self.px(self.MENU_SIDE), pady=(self.px(26), self.px(28)))
        tk.Frame(wrap, bg=BG, width=width, height=0).pack()
        return wrap

    def _menu_resized(self):
        """Window resized: once it settles, re-lay out Home / the category list / Settings."""
        if self._menu_page() is None:
            return
        if getattr(self, "_menu_job", None):
            self.root.after_cancel(self._menu_job)

        def run():
            self._menu_job = None
            page = self._menu_page()
            if page is None:
                return
            if self._menu_layout(page) != getattr(self, "_menu_fit", None):
                {"home": self.show_launcher, "settings": self.show_settings,
                 "picker": lambda: self.show_picker(self.mode)}[page]()
        self._menu_job = self.root.after(150, run)

    def show_launcher(self):
        """Home screen: the two things you can do."""
        self._stash()
        self.mode, self.cat, self.view = "home", None, None
        stage = self._new_stage()
        self.root.title(APP_TITLE)
        self._draw_chrome()
        k, width = self._menu_fit = self._menu_layout("home")
        with self._zoomed(k):
            wrap = self._menu_wrap(stage, width)
            self.label(wrap, "In Like Flint", 11, MUTED, True, bg=BG, anchor="w").pack(anchor="w")
            self.label(wrap, "Load Lore", 20, TEXT, True, bg=BG, anchor="w").pack(anchor="w")
            self.label(wrap, "Explore the velocity, energy, recoil and cost of over 3,500 commercially "
                       "available rounds, or put loads head to head.", 11, MUTED, bg=BG, anchor="w", justify="left",
                       wraplength=width).pack(anchor="w", pady=(self.px(8), self.px(18)))
            for key, title, blurb in TOOLS:
                self._feature_card(wrap, key, title, blurb, lambda t=key: self.show_picker(t),
                                   width).pack(fill="x", pady=(0, self.px(10)))
            note = tk.Frame(wrap, bg=BG)
            note.pack(anchor="w", pady=(self.px(4), 0))
            self.label(note, "Figures are estimates. Nothing you see here is reloading data. ", 10, MUTED,
                       bg=BG).pack(side="left")
            go = tk.Label(note, text="Disclaimer in Settings ›", bg=BG, fg=ACCENT,
                          font=self.f(10, True), cursor="hand2")
            go.pack(side="left")
            go.bind("<Button-1>", lambda e: self.show_settings())
        self._update_scroll()

    def _feature_card(self, parent, key, title, blurb, command, width):
        """A Home card like the web's .fcard on a PC: accent icon tile beside the title and a
        line about it (desktop-app sized, Zeke, Oct 25 2026)."""
        card = RoundBox(parent, self, SURFACE, BORDER, radius=12, padx=18, pady=16, cursor="hand2")
        tile = RoundBox(card.body, self, ACCENT, ACCENT, radius=9, padx=8, pady=8, cursor="hand2")
        tile.pack(side="left", anchor="n")
        ic = tk.Label(tile.body, image=self.icon(key, ON_ACCENT, 20), bg=ACCENT, cursor="hand2",
                      bd=0, padx=0, pady=0)
        ic.pack()
        text = tk.Frame(card.body, bg=SURFACE, cursor="hand2")
        text.pack(side="left", fill="x", expand=True, padx=(self.px(14), 0))
        t = tk.Label(text, text=title, bg=SURFACE, fg=TEXT, font=self.f(12, True), anchor="w",
                     cursor="hand2")
        t.pack(fill="x")
        d = tk.Label(text, text=blurb, bg=SURFACE, fg=MUTED, font=self.f(10), anchor="w",
                     justify="left", cursor="hand2",
                     wraplength=width - 2 * self.px(18) - self.px(36 + 14) - 4)
        d.pack(fill="x", pady=(self.px(2), 0))
        parts = (text, t, d)
        card.on_click(command, (tile, tile.canvas, tile.body, ic, *parts))
        for w in (card, card.canvas, card.body, tile, tile.canvas, tile.body, ic,
                  *parts):
            w.bind("<Enter>", lambda e: card.recolour(SURFACE_2, ACCENT, parts))
            w.bind("<Leave>", lambda e: card.recolour(SURFACE, BORDER, parts))
        return card

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
        def flip():
            self.set_check_on_start(not self.check_on_start)
            paint()

        def paint():
            on = self.check_on_start
            chip.set(text="On" if on else "Off", kind="on" if on else "chip")
        chip = toggle(self, box, flip)
        paint()
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
        k, width = self._menu_fit = self._menu_layout("settings")
        text_size = f"{round(self.scale * 100)}%"
        with self._zoomed(k):
            self._settings_page(stage, width, text_size)
        self._update_scroll()

    def _settings_page(self, stage, width, text_size):
        wrap = self._menu_wrap(stage, width)
        self.label(wrap, "Settings", 17, TEXT, True, bg=BG, anchor="w").pack(anchor="w")

        def section(title):
            """A titled box; its rows are split by thin lines instead of each having a box."""
            self.label(wrap, title, 10, MUTED, True, bg=BG, anchor="w").pack(
                anchor="w", pady=(self.px(10), self.px(6)))
            box = self.card(wrap, padx=16, pady=2)
            box.pack(fill="x", pady=(0, self.px(6)))
            card = box.body
            card.rows = 0
            return card

        def line(card):
            if card.rows:
                tk.Frame(card, bg=BORDER, height=1).pack(fill="x")
            card.rows += 1

        def row(title, note=None):
            line(card)
            r = tk.Frame(card, bg=SURFACE)
            r.pack(fill="x")
            text = tk.Frame(r, bg=SURFACE)
            text.pack(side="left", fill="x", expand=True, pady=self.px(12))
            self.label(text, title, 11, TEXT, True, bg=SURFACE, anchor="w").pack(anchor="w")
            if note:
                self.label(text, note, 9, MUTED, bg=SURFACE, anchor="w").pack(anchor="w")
            right = tk.Frame(r, bg=SURFACE)
            right.pack(side="right", pady=self.px(10))
            return right

        card = section("Display")
        theme_var = tk.StringVar(value=self.theme)
        pbox, pick = self.field(row("Theme"), ttk.Combobox, textvariable=theme_var,
                                font=self.f(11), width=max(len(n) for n in THEMES) + 2)
        pbox.pack()
        pick.theme_var = theme_var                    # keep the variable alive with its box
        LoadSearch(self, pick, list(THEMES), self.set_theme)
        box = row("Text size", text_size)
        for text, delta in (("A−", -0.15), ("A+", 0.15)):
            self.button(box, text, lambda d=delta: self.set_scale(self.scale + d), size=11,
                        padx=13, pady=6).pack(side="left", padx=(self.px(6), 0))

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
        self.label(card, "Disclaimer", 11, TEXT, True, bg=SURFACE, anchor="w").pack(
            anchor="w", pady=(self.px(12), 0))
        about = self.label(card, ABOUT_TEXT, 9, MUTED, bg=SURFACE, anchor="w", justify="left",
                           wraplength=width - 2 * self.px(16) - 4)
        about.pack(fill="x", pady=(self.px(2), self.px(12)))
        self.label(row("Version"), version_text(), 9, MUTED, bg=SURFACE).pack()

    def _stash(self):
        """Remember what the open tool has on screen, for when you come back to it."""
        if self.view is None:
            return
        if self.view.tab == "hand":
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

    def show_hand(self, open_id=None):
        """The Handloads tab: every handload of every category; `open_id` opens that one."""
        self._stash()
        self.mode, self.cat, self.view = "hand", None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {tool_title('hand')}")
        self._draw_chrome()
        self.view = HandloadsView(self, stage, open_id)
        self._update_scroll()

    def show_picker(self, mode):
        """Choose a category for the Load Dictionary (Head to Head has no categories)."""
        if mode == "h2h":
            return self.show_h2h()
        if mode == "hand":
            return self.show_hand()
        self._stash()
        self.mode, self.cat, self.view = mode, None, None
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {tool_title(mode)}")
        self._draw_chrome()
        k, width = self._menu_fit = self._menu_layout("picker")
        with self._zoomed(k):
            self._picker_page(stage, mode, width)
        self._update_scroll()

    def _picker_page(self, stage, mode, width):
        wrap = self._menu_wrap(stage, width)
        self.label(wrap, tool_title(mode), 17,
                   TEXT, True, bg=BG, anchor="w").pack(anchor="w")
        self.label(wrap, "Choose a category.", 11, MUTED, bg=BG, anchor="w").pack(
            anchor="w", pady=(self.px(4), self.px(18)))
        def counts(cats):
            carts, n = set(), 0
            for cat in cats:
                info = self.data[cat.title]
                if info["error"]:
                    return "Data file missing" if "not found" in info["error"] else "Data problem"
                carts |= {x.cartridge for x in info["detail"]}
                if cat.grain_style:                          # + cartridges open to handloads only
                    carts |= {x.cartridge for x in info["loads"]}
                n += len(info["detail"])
            return f"{len(carts)} cartridges · {n:,} loads"

        def card(title, blurb, caption, click, sub=0):
            box = RoundBox(wrap, self, SURFACE, BORDER, radius=12, padx=18, pady=14, cursor="hand2")
            box.pack(fill="x", pady=(0, self.px(10)), padx=(sub, 0))
            t = tk.Label(box.body, text=title, bg=SURFACE, fg=TEXT, font=self.f(12, True),
                         anchor="w", cursor="hand2")
            t.pack(fill="x")
            d = tk.Label(box.body, text=blurb, bg=SURFACE, fg=MUTED, font=self.f(10), anchor="w",
                         justify="left", wraplength=width - sub - 2 * self.px(18) - 4, cursor="hand2")
            d.pack(fill="x", pady=(self.px(2), self.px(8)))
            c = tk.Label(box.body, text=caption, bg=SURFACE, fg=ACCENT, font=self.f(9, True),
                         anchor="w", cursor="hand2")
            c.pack(fill="x")
            parts = (t, d, c)
            box.on_click(click, parts)
            for w in (box, box.canvas, box.body, *parts):
                w.bind("<Enter>", lambda e, cd=box, p=parts: cd.recolour(SURFACE_2, ACCENT, p))
                w.bind("<Leave>", lambda e, cd=box, p=parts: cd.recolour(SURFACE, BORDER, p))

        for entry in menu_entries():
            if not isinstance(entry, tuple):
                card(entry.title, entry.blurb, counts([entry]),
                     lambda ct=entry: self.go(ct, mode))
                continue
            # Handgun: a drop-down; its categories show indented under it once it is clicked
            name, cats = entry
            shown = name in self.open_groups
            card(f"{name}  {'▾' if shown else '▸'}", GROUP_BLURBS.get(name, ""), counts(cats),
                 lambda n=name: self._toggle_group(n))
            for cat in cats if shown else []:
                card(cat_name(cat), cat.blurb, counts([cat]), lambda ct=cat: self.go(ct, mode),
                     sub=self.px(28))

    def header(self, parent, cat, active):
        """Back link and the page title."""
        box = tk.Frame(parent, bg=BG)
        back = tk.Label(box, text="‹  Categories", bg=BG, fg=ACCENT, font=self.f(10, True),
                        cursor="hand2")
        back.grid(row=0, column=0, sticky="w")
        back.bind("<Button-1>", lambda e: self.show_picker(active))
        back.bind("<Enter>", lambda e: back.config(fg=ACCENT_HOVER))
        back.bind("<Leave>", lambda e: back.config(fg=ACCENT))
        title = tool_title(active)
        self.label(box, f"{title} · {cat_name(cat)}", 17, TEXT, True, bg=BG).grid(
            row=1, column=0, sticky="w", pady=(self.px(4), 0))
        return box

    def go(self, cat, tab):
        """Open a category in a feature, remembering what each tab had on screen."""
        if tab == "h2h":
            return self.show_h2h()
        self._stash()
        if cat.group:                      # back on the category list, its drop-down is open
            self.open_groups.add(cat.group)
        mem = self.carry.get(cat.title)
        self.open_category(cat, tab, dict(mem) if mem else None)

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
        self.root.title(f"{APP_TITLE} — {cat_name(cat)}")
        self._draw_chrome()
        self.view = LoadsView(self, stage, cat, info["detail"] + self.hand_loads(cat),
                              info["detail_error"], snap)
        self._update_scroll()


def handload_cartridges(app):
    """Every cartridge a handload can be for, across the bullet categories: {text: (category,
    cartridge)}; a cartridge in two categories (9mm Luger) gets its category's tag ("9mm Luger  ·
    Carbine"). The pop-up lists just the cartridge, under its category's heading (Zeke)."""
    per = []
    for cat in CATEGORIES:
        info = app.data.get(cat.title, {})
        if not cat.grain_style or info.get("error"):
            continue
        groups = with_handload_only(group_by_cartridge(info["detail"] + app.hand_loads(cat), True),
                                    info["loads"])
        per.append((cat, list(groups)))
    count = {}
    for _, carts in per:
        for c in carts:
            count[c] = count.get(c, 0) + 1
    return {(f"{c}  ·  {CAT_TAGS.get(cat.title, cat.title)}" if count[c] > 1 else c): (cat, c)
            for cat, carts in per for c in carts}


def disclaimer(app, parent, bg):
    """The handload safety note under a bold DISCLAIMER heading (Zeke), wrapping to its width."""
    app.label(parent, "DISCLAIMER", 9, TEXT, True, bg=bg, anchor="w").pack(anchor="w")
    text = app.label(parent, HANDLOAD_NOTE, 9, MUTED, bg=bg, anchor="w", justify="left",
                     wraplength=app.px(420))     # until it knows its width; never widens the window
    text.pack(fill="x", pady=(2, 0))
    text.bind("<Configure>", lambda e: text.configure(wraplength=max(e.width, 1)))


def open_handload_dialog(app, parent, existing=None, duplicate=False, on_saved=None):
    """The Handloads tab's add / edit form, for any category (the cartridge picks it).
    `existing` is a handload record (dict) to start from."""
    win = tk.Toplevel(parent)
    win.configure(bg=BG)
    win.title("Edit handload" if existing and not duplicate else "New handload")
    opts = handload_cartridges(app)

    def pick_of(text):
        text = text.strip()
        low = text.lower()
        for t, v in opts.items():
            if t == text:
                return v
        for t, v in opts.items():
            if t.lower() == low or v[1].lower() == low:
                return v
        return None
    win.transient(parent)
    win.resizable(False, False)
    card = app.card(win, padx=4, pady=4)
    card.pack(padx=16, pady=16, fill="both")
    body = card.body
    for c in range(3):
        body.columnconfigure(c, weight=1, uniform="c")
    ex = dict(existing or {})
    if ex.get("cartridge"):                           # its text in the cartridge list
        ex["cartridge"] = next((t for t, (c, x) in opts.items() if x == ex["cartridge"] and
                                c.title == ex.get("category")), ex["cartridge"])
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
    bullets = app.bullets

    def lab(text, row, col, span=1, pady=(10, 3)):
        app.label(body, text, 9, MUTED, True).grid(
            row=row, column=col, columnspan=span, sticky="w", pady=pady,
            padx=(18 if col == 0 else 6, 6 if col + span < 3 else 18))

    def ent(var, row, col, span=1, kind="entry"):
        px = dict(padx=(18 if col == 0 else 6, 6 if col + span < 3 else 18))
        if kind == "combo":                           # a box that opens a search pop-up
            box, w = app.field(body, ttk.Combobox, textvariable=var, font=app.f(11), width=8)
        else:
            box, w = app.field(body, ttk.Entry, textvariable=var, font=app.f(11), width=8)
        box.grid(row=row, column=col, columnspan=span, sticky="ew", **px)
        return w

    def section(text, row):
        tk.Frame(body, bg=BORDER, height=1).grid(row=row, column=0, columnspan=3, sticky="ew",
                                                 padx=18, pady=(16, 0))
        app.label(body, text, 9, ACCENT, True).grid(row=row + 1, column=0, columnspan=3,
                                                    sticky="w", padx=18, pady=(8, 0))

    lab("CARTRIDGE", 0, 0, 2, (16, 3))
    lab("PURPOSE", 0, 2, 1, (16, 3))
    cart_box = ent(V["cartridge"], 1, 0, 2, "combo")
    LoadSearch(app, cart_box, list(opts), lambda n: refresh_bullets(),
               head=lambda t: cat_name(opts[t][0]), label=lambda t: opts[t][1], hint="Cartridge")
    LoadSearch(app, ent(V["purpose"], 1, 2, 1, "combo"), list(PURPOSES), lambda n: None,
               hint="Purpose")
    lab("LOAD NAME (OPTIONAL)", 2, 0, 3)
    ent(V["name"], 3, 0, 3)

    section("BULLET", 4)
    lab("MAKER", 6, 0, 1, (6, 3))
    lab("BULLET", 6, 1, 2, (6, 3))
    # pick from the library, or type your own maker / bullet / powder
    maker_search = LoadSearch(app, ent(V["bullet_maker"], 7, 0, 1, "combo"), [],
                              lambda n: (V["bullet"].set(""), refresh_bullets()),
                              hint="Bullet maker", own=True)
    bullet_search = LoadSearch(app, ent(V["bullet"], 7, 1, 2, "combo"), [],
                               lambda n: pick_bullet(), hint="Bullet", own=True)
    lab("WEIGHT (GR)", 8, 0)
    lab("DIAMETER (IN)", 8, 1)
    lab("BC (G1)", 8, 2)
    ent(V["bullet_gr"], 9, 0)
    ent(V["diameter_in"], 9, 1)
    ent(V["bc_g1"], 9, 2)
    note = app.label(body, "Pick a maker and bullet to fill these in, or type your own. Leave "
                           "diameter / BC blank to estimate them.", 9, MUTED, anchor="w")
    note.grid(row=10, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 0))

    section("POWDER AND PERFORMANCE", 11)
    lab("POWDER", 13, 0, 1, (6, 3))
    lab("CHARGE (GR)", 13, 1, 1, (6, 3))
    lab("MUZZLE VELOCITY (FPS)", 13, 2, 1, (6, 3))
    LoadSearch(app, ent(V["powder"], 14, 0, 1, "combo"), list(POWDERS), lambda n: None,
               hint="Powder", own=True)
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
    note = tk.Frame(body, bg=body.cget("bg"))
    note.grid(row=26, column=0, columnspan=3, sticky="ew", padx=18, pady=(10, 0))
    disclaimer(app, note, body.cget("bg"))

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

    def fits(b):
        """The library bullet is the cartridge's diameter (bullets go by diameter, not cartridge)."""
        pick = pick_of(V["cartridge"].get())
        d = DIAMETERS.get(pick[1]) if pick else None
        return not d or abs(b["diameter"] - d) <= 0.003

    def refresh_bullets(*_):
        """Makers list only those with a bullet of this diameter; bullets only the picked maker's."""
        maker = V["bullet_maker"].get().strip()
        maker_search.names = sorted({b["maker"] for b in bullets if fits(b)})
        bullet_search.names = [f"{b['name']} · {b['weight']:g} gr" for b in bullets
                               if b["maker"] == maker and fits(b)]

    def pick_bullet(*_):
        maker, label = V["bullet_maker"].get().strip(), V["bullet"].get()
        for b in bullets:
            if b["maker"] == maker and f"{b['name']} · {b['weight']:g} gr" == label and fits(b):
                V["bullet_gr"].set(f"{b['weight']:g}")
                V["diameter_in"].set(f"{b['diameter']:g}")
                V["bc_g1"].set(f"{b['bc']:g}")
                V["bullet"].set(label)
                break

    V["cartridge"].trace_add("write", refresh_bullets)
    V["bullet_maker"].trace_add("write", refresh_bullets)
    for k in ("bullet_cost", "powder_cost_lb", "powder_gr", "primer_cost", "brass_cost",
              "brass_reuse", "total"):
        V[k].trace_add("write", update_cost)
    refresh_bullets()
    update_cost()

    def save(_e=None):
        try:
            pick = pick_of(V["cartridge"].get())
            if pick is None:
                raise ValueError("Pick a cartridge from the list." if V["cartridge"].get().strip()
                                 else "Enter a cartridge.")
            cat, cart = pick
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
                bc = estimate_bc(gr, dia, cat.group == "Handgun")
            # saved as plain numbers: a typed "$0.30" or a stray letter used to be kept as typed,
            # and opening the handload in the Handloads tab then failed
            parts = {k: num(k, label, lo, hi, True) for k, label, lo, hi in (
                ("bullet_cost", "Bullet cost", 0, None), ("powder_cost_lb", "Powder cost", 0, None),
                ("primer_cost", "Primer cost", 0, None), ("brass_cost", "Brass cost", 0, None),
                ("brass_reuse", "Brass reloads", 1, 1000))}
            total = num("total", "Total cost", 0, blank=True)
            cost = parts_cost() if total is None else total
            if not cost or cost <= 0:
                raise ValueError("Enter what a round costs (the parts, or a total per round).")
        except ValueError as exc:
            messagebox.showerror("Check your input", str(exc), parent=win)
            return
        row = dict(id=ex.get("id") if existing and not duplicate else new_handload_id(),
                   category=cat.title, cartridge=cart, name=V["name"].get().strip(),
                   bullet_maker=V["bullet_maker"].get().strip(),
                   bullet=V["bullet"].get().split(" · ")[0].strip(),
                   bullet_gr=f"{gr:g}", diameter_in=f"{dia:g}", bc_g1=f"{bc:g}",
                   powder=V["powder"].get().strip(), powder_gr=f"{charge:g}", muzzle_fps=f"{fps:g}",
                   barrel_in=f"{barrel:g}" if barrel else "", purpose=V["purpose"].get(),
                   cost=f"{cost:.4f}", notes=V["notes"].get().strip(),
                   **{k: "" if v is None else f"{v:g}" for k, v in parts.items()})
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
    chip = toggle(app, parent, command)
    style_grades_chip(app, chip)
    return chip


def style_grades_chip(app, chip):
    chip.set(text="On" if app.show_grades else "Off", kind="on" if app.show_grades else "chip")


def entry_hint(app, entry, var, text):
    """Grey text in an empty entry, like the web's placeholder (gone while it has the focus)."""
    hint = tk.Label(entry, text=text, bg=SURFACE_2, fg=MUTED, font=app.f(12), padx=0, pady=0,
                    cursor="xterm")
    hint.bind("<Button-1>", lambda e: entry.focus_set())

    def show(*_):
        if not hint.winfo_exists():
            return
        if var.get() or entry.focus_get() is entry:
            hint.place_forget()
        else:
            hint.place(x=app.px(5), rely=0.5, anchor="w")
    var.trace_add("write", show)
    entry.bind("<FocusIn>", show, add="+")
    entry.bind("<FocusOut>", show, add="+")
    show()
    return hint


def toggle(app, parent, command):
    """An On / Off pill like the web's .tgl switch."""
    return Pill(parent, app, "Off", command, "chip", size=9, padx=12, pady=5, radius=99)


def close_button(app, parent, command):
    """A ✕ that gets a rounded grey square under the pointer (the web's .x buttons)."""
    bg = parent.cget("bg")
    box = RoundBox(parent, app, bg, outside=bg, radius=8, padx=6, pady=2, cursor="hand2")
    x = tk.Label(box.body, text="✕", bg=bg, fg=MUTED, font=app.f(12, True), cursor="hand2",
                 bd=0, padx=2, pady=0)
    x.pack()
    box.on_click(command, (x,))
    for w in (box, box.canvas, box.body, x):
        w.bind("<Enter>", lambda e: (box.recolour(SURFACE_2, SURFACE_2, (x,)), x.config(fg=TEXT)))
        w.bind("<Leave>", lambda e: (box.recolour(bg, bg, (x,)), x.config(fg=MUTED)))
    return box


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
        # "Firearm setup" drop-down (Zeke, Oct 29 2026): gun weight, barrel length and twist rate;
        # a blank barrel or twist = the listed figures, anything typed makes them estimates
        self.fire_open, self.barrel, self.twist = False, 0.0, 0.0
        self.barrel_var = tk.StringVar(value="")
        self.twist_var = tk.StringVar(value="")
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
            for var in (self.dist_var, self.gun_var, self.barrel_var, self.twist_var, self.filter_var,
                        *self.weight_vars.values()):
                var.trace_add("write", self._schedule)
            self.weight_vars_note()
            # the box starts empty (Zeke, Oct 29 2026): only a cartridge picked earlier while the
            # app is open comes back
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
            mbox = a.card(outer, padx=4, pady=4)
            mbox.grid(row=3, column=0, sticky="ew")
            msg = mbox.body
            a.label(msg, error or "No loads found.", 11, TEXT, True, anchor="w").pack(
                anchor="w", padx=18, pady=(16, 4))
            a.label(msg, f"Put {cat.loads_filename} next to the program to use this tab.",
                    10, MUTED, anchor="w").pack(anchor="w", padx=18, pady=(0, 16))
            return

        box = a.card(outer, padx=18, pady=16)
        box.grid(row=3, column=0, sticky="ew")
        card = box.body
        card.columnconfigure(0, weight=1)
        pad = dict(padx=0)
        # the web's layout: the cartridge on its own line, distance and gun weight under it
        top = tk.Frame(card, bg=SURFACE)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure((0, 1), weight=1, uniform="n")
        a.label(top, cat.cartridge_label, 8, MUTED, True).grid(row=0, column=0, columnspan=2,
                                                                sticky="w")
        # the cartridge menu opens a search pop-up: type "6.5" or "mag" to narrow it down
        cbox, self.cart_combo = a.field(top, ttk.Combobox, textvariable=self.cart_var,
                                        values=self.cartridges, font=a.f(12),
                                        width=max([16] + [len(c) for c in self.cartridges]))
        cbox.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(a.px(5), 0))
        self.cart_search = LoadSearch(a, self.cart_combo, self.cartridges,
                                      lambda n: self._on_cartridge(),
                                      hint=cat.cartridge_label.capitalize())
        a.label(top, "DISTANCE (YD)", 8, MUTED, True).grid(row=2, column=0, sticky="w",
                                                            padx=(0, a.px(4)), pady=(a.px(14), 0))
        a.field(top, ttk.Entry, textvariable=self.dist_var, font=a.f(12), width=10)[0].grid(
            row=3, column=0, sticky="ew", padx=(0, a.px(4)), pady=(a.px(5), 0))
        # "Firearm setup": a drop-down box whose text sums up the gun; it opens the boxes under it
        a.label(top, "FIREARM SETUP", 8, MUTED, True).grid(row=2, column=1, sticky="w",
                                                           padx=(a.px(4), 0), pady=(a.px(14), 0))
        self.fire_btn = RoundBox(top, a, SURFACE_2, BORDER, radius=8, padx=10, pady=7,
                                 cursor="hand2")
        self.fire_btn.grid(row=3, column=1, sticky="ew", padx=(a.px(4), 0), pady=(a.px(5), 0))
        self.fire_btn.body.columnconfigure(0, weight=1)
        self.fire_lbl = tk.Label(self.fire_btn.body, text="", bg=SURFACE_2, fg=TEXT, font=a.f(12),
                                 anchor="w", cursor="hand2")
        self.fire_lbl.grid(row=0, column=0, sticky="ew")
        self.fire_arrow = tk.Label(self.fire_btn.body, text="▾", bg=SURFACE_2, fg=MUTED,
                                   font=a.f(11), cursor="hand2")
        self.fire_arrow.grid(row=0, column=1, sticky="e")
        self.fire_btn.on_click(self._toggle_fire, (self.fire_lbl, self.fire_arrow))
        self.fire_wrap = RoundBox(top, a, BG, BORDER, radius=10, padx=12, pady=12)
        self.fire_wrap.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(a.px(12), 0))
        self.fire_box = self.fire_wrap.body
        boxes = [(cat.gun_label, self.gun_var, None)]
        if cat.barrel_in:
            boxes += [("BARREL LENGTH (IN)", self.barrel_var, "Listed"),
                      ("TWIST RATE (1 IN … IN)", self.twist_var, "Not checked")]
        for i, (text, var, hint) in enumerate(boxes):
            self.fire_box.columnconfigure(i, weight=1, uniform="f")
            gap = (0 if i == 0 else a.px(4), 0 if i == len(boxes) - 1 else a.px(4))
            a.label(self.fire_box, text, 8, MUTED, True, bg=BG).grid(row=0, column=i, sticky="w",
                                                                   padx=gap)
            fbox, entry = a.field(self.fire_box, ttk.Entry, textvariable=var, font=a.f(12), width=8)
            fbox.grid(row=1, column=i, sticky="ew", padx=gap, pady=(a.px(5), 0))
            if hint:
                entry_hint(a, entry, var, hint)
        if len(boxes) < 3:
            for i in range(len(boxes), 3):
                self.fire_box.columnconfigure(i, weight=1, uniform="f")
        self.fire_note = a.label(self.fire_box, firearm_note(cat), 9, MUTED, bg=BG, anchor="w",
                                 justify="left", wraplength=a.px(640))
        self.fire_note.grid(row=2, column=0, columnspan=3, sticky="w", pady=(a.px(8), 0))
        self.fire_reset = tk.Label(self.fire_box, text="Reset to maker's figures" if cat.barrel_in
                                   else "Reset to the usual gun weight", bg=BG,
                                   fg=ACCENT, font=a.f(10, True), cursor="hand2")
        self.fire_reset.grid(row=3, column=0, columnspan=3, sticky="w", pady=(a.px(4), 0))
        self.fire_reset.bind("<Button-1>", lambda e: self._reset_fire())
        self.fire_wrap.grid_remove()
        self._style_fire()
        self.chip_row = tk.Frame(card, bg=SURFACE)
        self.chip_row.grid(row=5, column=0, sticky="w", pady=(a.px(12), 0), **pad)
        self.src_row = tk.Frame(card, bg=SURFACE)
        self.src_row.grid(row=6, column=0, sticky="w", pady=(a.px(6), 0), **pad)
        self.status = a.label(card, "", 10, DANGER, anchor="w")
        self.status.grid(row=1, column=0, sticky="w", **pad)
        self.weights_toggle = tk.Label(card, text="▸  Scoring weights", bg=SURFACE, fg=MUTED,
                                       font=a.f(10, True), cursor="hand2")
        self.weights_toggle.grid(row=7, column=0, sticky="w", pady=(a.px(10), 0), **pad)
        self.weights_toggle.bind("<Button-1>", lambda e: self._toggle_weights())
        right = tk.Frame(card, bg=SURFACE)
        right.grid(row=7, column=0, sticky="e", pady=(a.px(10), 0), **pad)
        if cat.grain_style:
            add = tk.Label(right, text="Your handloads ›", bg=SURFACE, fg=ACCENT, font=a.f(10, True),
                           cursor="hand2")                 # adding / editing lives in the Handloads tab
            add.pack(side="left")
            add.bind("<Button-1>", lambda e: a.show_hand())
        self.weights_frame = tk.Frame(card, bg=SURFACE)
        for i, key in enumerate(self.keys):
            a.label(self.weights_frame, METRICS[key][0], 9, MUTED).grid(
                row=0, column=i, sticky="w", padx=(0 if i == 0 else a.px(8), 0))
            wbox, _ = a.field(self.weights_frame, ttk.Spinbox, from_=0, to=10, increment=1, width=3,
                              textvariable=self.weight_vars[key], font=a.f(11))
            wbox.grid(row=1, column=i, sticky="ew", padx=(0 if i == 0 else a.px(8), 0),
                      pady=(a.px(4), 0))
        self.weight_note = a.label(self.weights_frame, "", 9, TEXT, True)
        self.weight_note.grid(row=2, column=0, columnspan=12, sticky="w", pady=(8, 0))
        self.weights_frame.grid(row=8, column=0, sticky="w", pady=(8, 0), **pad)
        self.weights_frame.grid_remove()

        # ---- ranked table
        tbl = tk.Frame(outer, bg=BG)
        tbl.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        tbl.columnconfigure(0, weight=1)
        # the brand / load filter sits right above the list it filters (issue #26); label over
        # the box like the fields in the card, the load count level with the box
        above = tk.Frame(tbl, bg=BG)
        above.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        above.columnconfigure(1, weight=1)
        a.label(above, "FILTER BRAND / LOAD", 8, MUTED, True, bg=BG).grid(row=0, column=0, sticky="w")
        fl = tk.Frame(above, bg=BG)
        fl.grid(row=1, column=0, sticky="w", pady=(a.px(5), 0))
        a.field(fl, ttk.Entry, textvariable=self.filter_var, font=a.f(11), width=28)[0].pack(
            side="left")
        # +P / +P+ check boxes, only for cartridges that have such loads
        self.press_row = tk.Frame(fl, bg=BG)
        self.press_row.pack(side="left", padx=(14, 0))
        self.count_lbl = a.label(above, self._choose_text(),
                                 10, MUTED, bg=BG, anchor="e")
        self.count_lbl.grid(row=1, column=1, sticky="e", pady=(4, 0), padx=(16, 0))
        # bullets get a Grains column (the Load cell then shows just the name)
        self.cols = ["#", "Load"] + (["Grains"] if cat.grain_style else ["Shot", cat.payload_col])
        if cat.grain_style:
            self.cols += ["Barrel", "Use"]
        self.cols += ["Velocity", "Energy", "Recoil"]
        if cat.terminal:
            self.cols += ["Taylor", "HITS"]
        self.cols += ["Price", "Score", "Grade"]
        # the table sits in a rounded box like the web's tables
        tbox = a.card(tbl, radius=10, padx=3, pady=3)
        tbox.grid(row=1, column=0, sticky="nsew")
        frame = tbox.body
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
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
        self.tree.tag_configure("spin", foreground=DANGER)    # won't stabilise in the twist set
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        # ---- selected load
        self.detail = a.card(outer, padx=4, pady=4)
        d = self.detail.body
        d.columnconfigure(0, weight=1)
        self.d_title = a.label(d, "", 16, TEXT, True, anchor="w", justify="left",
                               wraplength=a.px(820))
        self.d_title.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        close_button(a, d, self._close_detail).grid(row=0, column=1, sticky="ne", padx=(0, 10),
                                                    pady=(10, 0))
        self.d_info = a.label(d, "", 12, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_info.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))
        # the four factors sit side by side, packed to the left (no stretched columns)
        factors = tk.Frame(d, bg=SURFACE)
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
            badge = Badge(line, a, "", 12)
            badge.pack(side="left", padx=(6, 0))
            self.d_badges[key] = (val, badge)
        priceline = tk.Frame(d, bg=SURFACE)
        self.priceline = priceline
        priceline.grid(row=3, column=0, sticky="w", padx=18, pady=(14, 0))
        self.handline = tk.Frame(d, bg=SURFACE)
        self.handline.grid(row=3, column=0, sticky="w", padx=18, pady=(14, 0))
        a.button(self.handline, "Edit in Handloads  ›",
                 lambda: a.show_hand(self.selected.hid if self.selected else None)).pack(side="left")
        self.handline.grid_remove()
        self.h2h_btn = a.button(d, "", self._h2h_click)
        self.h2h_btn.grid(row=3, column=0, columnspan=2, sticky="e", padx=18, pady=(14, 0))
        a.label(priceline, "YOUR PRICE PER ROUND ($)", 9, MUTED, True).pack(side="left")
        a.field(priceline, ttk.Entry, textvariable=self.price_var, width=8, font=a.f(11))[0].pack(
            side="left", padx=8)
        a.button(priceline, "Set price", self._set_price, "primary").pack(side="left")
        a.button(priceline, "Use catalog estimate", self._reset_price).pack(side="left", padx=8)
        self.d_note = a.label(d, "", 10, MUTED, anchor="w", justify="left",
                              wraplength=a.px(820))
        self.d_note.grid(row=4, column=0, sticky="w", padx=18, pady=(10, 6))
        self.bt_toggle = tk.Label(d, text="", bg=SURFACE, fg=ACCENT, font=a.f(11, True),
                                  cursor="hand2")
        self.bt_toggle.grid(row=5, column=0, sticky="w", padx=18, pady=(4, 14))
        self.bt_toggle.bind("<Button-1>", lambda e: self._toggle_ballistics())
        self.bt_frame = tk.Frame(d, bg=SURFACE)
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
                    fire_open=self.fire_open, barrel=self.barrel_var.get(),
                    twist=self.twist_var.get(),
                    weights={k: v.get() for k, v in self.weight_vars.items()},
                    weights_open=self.weights_open, purpose=self.purpose, source=self.source,
                    pressure={p: v.get() for p, v in self.press_vars.items()})

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
        if "barrel" in snap:
            self.barrel_var.set(snap["barrel"])
        if "twist" in snap:
            self.twist_var.set(snap["twist"])
        if snap.get("fire_open") and not self.fire_open:
            self._toggle_fire()
        if snap.get("weights_open") and not self.weights_open:
            self._toggle_weights()
        return snap.get("cart") if snap.get("cart") in self.groups else None

    # ---- helpers ---------------------------------------------------------- #
    def _toggle_fire(self):
        self.fire_open = not self.fire_open
        if self.fire_open:
            self.fire_wrap.grid()
        else:
            self.fire_wrap.grid_remove()
        self._style_fire()
        if hasattr(self, "tree"):
            self.fit_table_height()

    def _style_fire(self):
        """The drop-down box's summary: what the figures are for."""
        def num(var):
            try:
                return float(var.get())
            except ValueError:
                return 0.0
        self.fire_lbl.config(text=firearm_text(self.cat, num(self.gun_var), num(self.barrel_var),
                                               parse_twist(self.twist_var.get()) or 0))
        self.fire_arrow.config(text="▴" if self.fire_open else "▾")

    def _reset_fire(self):
        """Back to the listed figures: no barrel length or twist, the cartridge's usual gun."""
        self.barrel_var.set("")
        self.twist_var.set("")
        self._gun_auto = typical_gun_lb(self.cat, self.cart_var.get())
        self.gun_var.set(f"{self._gun_auto:g}")

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
            f"{REL_CENTER:.0f}). " if on else "") + "Prices are estimates: set your own."
            + (f" {self.cat.note}" if self.cat.note else ""))

    def _h2h_click(self):
        item = self.selected
        if item is None:
            return
        picks = self.app.h2h
        if pick_key(self.cat, item) in picks or len(picks) >= H2H_MAX:
            self.app.show_h2h()
            return
        self.app.add_to_h2h(self.cat, base_load(item))     # Head to Head keeps listed figures
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

    def _fire_count(self):
        """", 16 in barrel, 1:8 twist (estimates)" for the count line, or ""."""
        parts = ([f"{self.barrel:g} in barrel"] if self.barrel else []) + (
            [f"1:{self.twist:g} twist"] if self.twist else [])
        warn = ("  ·  ⚠ = spin too slow (red: won't stabilise)"
                if any(stability_warn(r["item"]) for r in self.rows) else "")
        return (f", {', '.join(parts)} (estimates)" if parts else "") + warn

    @staticmethod
    def _twist(var, name):
        """Inches per turn from "1:8", "1 in 8" or "8"."""
        v = parse_twist(var.get())
        if v is None or not TWIST_MIN <= v <= TWIST_MAX:
            raise ValueError(f"{name}: type the inches per turn, {TWIST_MIN:g}-{TWIST_MAX:g} "
                             "(1:8 or 8).")
        return v

    def _choose_text(self):
        return f"Choose a {self.cat.cartridge_label.lower()} to see how every brand's loads compare."

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
            cart = ""
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
        for name, n in (("All", len(items)), ("Factory", len(items) - nh), ("Handloads", nh)):
            chip = self.app.chip(self.src_row, name, lambda nm=name: self._pick_source(nm),
                                 note=str(n))
            chip.pack(side="left", padx=(0, self.app.px(6)))
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
            mark = RoundBox(row, self.app, BG, MUTED, radius=5, padx=2, pady=0, cursor="hand2")
            mark.pack(side="left")
            tick = tk.Label(mark.body, width=2, font=self.app.f(9, True), bg=BG, fg=ON_ACCENT,
                            bd=0, padx=0, pady=0, cursor="hand2")
            tick.pack()
            mark.tick = tick
            text = self.app.label(row, p, 10, TEXT, True, bg=BG)
            text.pack(side="left", padx=(self.app.px(7), 0))
            for w in (row, mark, mark.canvas, mark.body, tick, text):
                w.bind("<Button-1>", lambda e, pr=p: self._pick_pressure(pr))
            self.press_boxes[p] = (mark, text)
        self._style_pressure()

    def _style_pressure(self):
        for p, (mark, _) in self.press_boxes.items():
            on = self.press_vars[p].get()
            mark.tick.configure(text="✓" if on else "")
            mark.recolour(ACCENT if on else BG, ACCENT if on else MUTED, (mark.tick,))

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
        for name in names:
            n = len(items) if name == "All" else sum(self._purpose_of(x) == name for x in items)
            chip = self.app.chip(self.chip_row, name, lambda nm=name: self._pick_purpose(nm),
                                 note=str(n))
            chip.pack(side="left", padx=(0, self.app.px(6)))
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
            chip.set(note=str(n))
        shown = [x for x in items if self.source == "All" or x.handload == (self.source == "Handloads")]
        for name, chip in self.chips.items():
            n = len(shown) if name == "All" else sum(self._purpose_of(x) == name for x in shown)
            chip.set(note=str(n))

    def _style_chips(self):
        for name, chip in self.chips.items():
            chip.set(kind="on" if name == self.purpose else "chip")
        for name, chip in self.src_chips.items():
            chip.set(kind="on" if name == self.source else "chip")

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
        if hasattr(self, "fire_lbl") and self.fire_lbl.winfo_exists():
            self._style_fire()
        alive = getattr(self.tree, "winfo_exists", None)
        if alive is not None and not alive():          # a delayed refresh after leaving this tab
            return
        cart = self.cart_var.get()
        items = self.groups.get(cart)
        if items is None:                            # nothing picked yet
            self.tree.delete(*self.tree.get_children())
            self.rows = []
            self.count_lbl.config(text=self._choose_text())
            return
        if not items:                                # a cartridge with no factory loads yet
            self.tree.delete(*self.tree.get_children())
            self.rows = []
            self.selected = None
            self.detail.grid_remove()
            self.count_lbl.config(text=f"No factory loads listed for {cart}. Add your own in the "
                                       "Handloads tab to grade it.")
            return
        if self.purpose != "All":
            items = [x for x in items if self._purpose_of(x) == self.purpose]
        try:
            dist = self._num(self.dist_var, "Distance", 0, self.cat.max_distance)
            gun = self._num(self.gun_var, "Gun weight", 0.5, GUN_LB_MAX)
            barrel = (self._num(self.barrel_var, "Barrel length", BARREL_MIN, BARREL_MAX)
                      if self.cat.barrel_in and self.barrel_var.get().strip() else 0.0)
            twist = (self._twist(self.twist_var, "Twist rate")
                     if self.cat.barrel_in and self.twist_var.get().strip() else 0.0)
            weights = {k: self._num(v, f"{METRICS[k][0]} weight", 0, 10)
                       for k, v in self.weight_vars.items()}
        except ValueError as exc:
            self.status.config(text=str(exc))
            return
        self.status.config(text="")
        self.barrel, self.twist = barrel, twist
        items = [at_firearm(x, self.cat, barrel, twist) for x in items]
        self.rows = score_loads(items, dist, gun, weights,
                                [self.app.price_for(self.cat, x) for x in items],
                                by_type=not self.cat.grain_style)
        self.group_order = {k: n for n, k in enumerate(dict.fromkeys(r["group"] for r in self.rows))}
        for r in self.rows:
            r["custom_price"] = abs(r["stats"]["cost"] - r["item"].default_cost) > 1e-9
        self.dist = dist
        self._render()

    def _sort_by(self, col):
        first = col in ("Grains", "Shot", self.cat.payload_col, "Velocity", "Energy", "Taylor", "HITS", "Score")
        # clicking the sorted heading again goes back to the default order; Grains goes
        # heaviest, then lightest, then the default order (Zeke, Oct 28 2026; same as the web)
        if self.sort["col"] == col and col == "Grains" and self.sort["desc"]:
            self.sort["desc"] = False
        elif self.sort["col"] == col or col == "#":
            self.sort = {"col": "#", "desc": False}
        else:
            self.sort = {"col": col, "desc": first}
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
                "Grains": lambda r: r["item"].bullet_gr,
                # biggest shot first, then the most pellets, then the heaviest payload
                "Shot": lambda r: shot_size(r["item"])[:2] + (r["stats"]["weight"],),
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
            name = (it.load or it.label) if self.cat.grain_style else it.label
            vals = [r["rank"], name + ("  (handload)" if it.handload else "")
                    + ("  ⚠" if stability_warn(it) else "")]
            if self.cat.grain_style:
                vals += [f"{it.bullet_gr:g}", f"{it.barrel_in:g}\"" if it.barrel_in else "—", it.purpose]
            else:
                vals += [shot_size(it)[2], f"{st['weight']:g}"]
            vals += [f"{st['velocity']:.0f}", f"{st['energy']:.0f}", f"{st['recoil']:.1f}"]
            if self.cat.terminal:
                vals += [f"{st['taylor']:.1f}", f"{st['hits']:.0f}"]
            vals += [f"{st['cost']:.2f}" + (" ✎" if r["custom_price"] else ""),
                     f"{r['overall']:.0f}", r["grade"]]
            cells.append(vals)
            iid = self.tree.insert("", "end", values=vals, tags=(("hand",) if it.handload else ())
                                   + (("spin",) if getattr(it, "sg", 1) < SG_MIN else ()))
            self.iid_row[iid] = r
            if self.selected is not None and base_load(self.selected) is base_load(it):
                self.selected = it                # the same load at a new barrel length
                keep = iid
        self.count_lbl.config(
            text=f"{self.cart_var.get()}"
                 f"{'' if self.purpose == 'All' else '  ·  ' + self.purpose}: {len(data)} of "
                 f"{len(self.rows)} loads at {self.dist:g} yards"
                 + self._fire_count())
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
            if self.barrel:
                info.append(f"figures for a {self.barrel:g} in barrel (estimate)")
            if getattr(item, "sg", 0):
                info.append(f"stability {item.sg:.2f} in a 1:{item.twist:g} twist: "
                            f"{stability_text(item.sg)}")
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
            val.config(text=vals[key])
            if self.app.show_grades:
                badge.set(grade)
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
                row=0, column=c, sticky="e", padx=(0 if c == 0 else 26, 0), pady=(0, 6))
        a.rule(self.bt_frame, 0, len(heads))
        table = ballistic_table(item, cat)
        for r, (yd, v, e, path, drift) in enumerate(table, start=1):
            for c, text in enumerate((f"{yd:g}", f"{v:,.0f}", f"{e:,.0f}", "0.0" if abs(path) < 0.05 else f"{path:+.1f}",
                                      f"{drift:.1f}")):
                a.label(self.bt_frame, text, 11, TEXT, c == 0, anchor="e").grid(
                    row=r, column=c, sticky="e", padx=(0 if c == 0 else 26, 0), pady=4)
            if r < len(table):
                a.rule(self.bt_frame, r, len(heads))
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
            rowh = a.px(30)
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
            if self.selected is not None and base_load(r["item"]) is base_load(self.selected):
                self.tree.selection_set(iid)
                self._on_select()
                break


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    """A rectangle with rounded corners on a Canvas (a smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = (x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)
    return canvas.create_polygon(pts, smooth=True, **kw)


class LoadSearch:
    """A cartridge or load box that opens a search pop-up (issue #24; a pop-up since Oct 2026,
    the desktop match for the phone's bottom sheet): a click, Down, Enter or a typed letter on
    the box opens a panel under it with a search field (the cursor in it) over the list. Every
    typed word must appear in the name (brand, bullet, weight...); Up/Down move, Enter or a
    click picks, Esc or a click outside closes. The box itself takes no typing, so its text is
    never selected.
    names: the list. value(name): the box text once a name is picked (default: the name).
    browse: the order to list them in (default: names). head(name): a group heading over the
    rows (optional), label(name): a row's text (default: the name). on_pick(name) gets the
    pick; last is the box text of the last pick. hint: the grey text an empty box shows, like
    the web's placeholder (a string, or a function for one that changes). own: lets the user
    keep what they typed when it isn't in the list (a last row 'Use "..."'; makers, bullets and
    powders in the handload form)."""

    def __init__(self, app, box, names, on_pick, value=None, head=None, label=None, hint=None,
                 own=False):
        self.app, self.box, self.names, self.on_pick = app, box, names, on_pick
        self.value = value or (lambda n: n)
        self.head, self.label = head, label or (lambda n: n)
        self.browse = None                # None: the same as names
        self.var = box.cget("textvariable")
        self.popup = self.entry = self.canvas = self.bar = None
        self.rows, self.texts, self.tops, self.at, self.total = [], [], [], None, 0
        # rows: a name, or None for a heading / the no-match line; tops: each row's y
        self.last = ""
        box.bind("<Button-1>", self._click)
        box.bind("<Key>", self._key)
        for ev in ("<<Paste>>", "<<Cut>>", "<<Clear>>"):
            box.bind(ev, lambda e: "break")
        self.hint, self.own = hint, own
        self.hint_label = None
        if hint is not None:
            self.hint_label = tk.Label(box, bg=SURFACE_2, fg=MUTED, font=box.cget("font"),
                                       cursor="hand2", padx=0, pady=0)
            self.hint_label.bind("<Button-1>", self._click)
            box.tk.call("trace", "add", "variable", self.var, "write",
                        box.register(lambda *x: self.show_hint()))
            self.show_hint()

    def show_hint(self):
        """Shows the hint while the box is empty (call it again when a hint function would
        give a different text)."""
        h = self.hint_label
        if h is None or not h.winfo_exists():
            return
        if self.text():
            h.place_forget()
        else:
            h.config(text=self.hint() if callable(self.hint) else self.hint)
            h.place(x=self.app.px(5), rely=0.5, anchor="w")

    def text(self):
        return self.box.tk.globalgetvar(self.var)

    def _click(self, e):
        if str(self.box.cget("state")) != "disabled":
            self.box.focus_set()
            self.open()
        return "break"

    def _key(self, e):
        if e.keysym in ("Tab", "ISO_Left_Tab", "Escape") or str(self.box.cget("state")) == "disabled":
            return None
        if e.keysym in ("Down", "Up", "Return", "KP_Enter", "space"):
            self.open()
        elif e.char and e.char.isprintable() and not e.state & 0x4:   # a letter starts a search
            self.open(e.char)
        return "break"

    def _find(self, text):
        words = text.lower().split()
        order = self.names if self.browse is None else self.browse
        return [n for n in order if all(w in n.lower() for w in words)]

    def open(self, typed=""):
        if self.popup is not None or not (self.names or self.own):
            return
        a = self.app
        # drawn like a refined menu (and like the web version): a rounded search field with a
        # magnifier, rows without lines, a rounded highlight set in from the edges, a check on
        # the current pick, quiet headings, and a thin scrollbar in the theme's colours
        self.font, self.head_font = tkfont.Font(font=a.f(11)), tkfont.Font(font=a.f(8, True))
        self.row_h, self.head_h = a.px(34), a.px(30)
        self.pop_w, self.up = 0, None
        # drawn inside the box's own window (not a window of its own), so it moves with the
        # window and never floats over other apps after Alt+Tab
        self.popup = tk.Frame(self.box.winfo_toplevel(), bg=BORDER)
        frame = tk.Frame(self.popup, bg=SURFACE)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        field = tk.Canvas(frame, bg=SURFACE, height=a.px(38), highlightthickness=0, borderwidth=0)
        field.pack(fill="x", padx=a.px(8), pady=(a.px(8), a.px(6)))
        self.query = tk.StringVar(value=typed)
        self.entry = tk.Entry(field, textvariable=self.query, bg=SURFACE_2, fg=TEXT,
                              insertbackground=TEXT, relief="flat", font=a.f(11),
                              highlightthickness=0, borderwidth=0)
        hint = tk.Label(field, text="Search", bg=SURFACE_2, fg=MUTED, font=a.f(11), anchor="w")
        def draw_field(e=None):
            w, h, r = field.winfo_width(), field.winfo_height(), a.px(8)
            field.delete("deco")
            rounded_rect(field, 1, 1, w - 2, h - 2, r, fill=SURFACE_2, outline=ACCENT, tags="deco")
            cx, cy, cr = a.px(17), h / 2 - a.px(1), a.px(5)
            field.create_oval(cx - cr, cy - cr, cx + cr, cy + cr, outline=MUTED, width=a.px(2) / 1.2,
                              tags="deco")
            field.create_line(cx + cr * 0.7, cy + cr * 0.7, cx + cr * 1.7, cy + cr * 1.7,
                              fill=MUTED, width=a.px(2), capstyle="round", tags="deco")
            field.coords("entry", a.px(32), h / 2)
            field.itemconfig("entry", width=max(10, w - a.px(42)))
        field.create_window(a.px(32), a.px(19), window=self.entry, anchor="w", tags="entry")
        field.bind("<Configure>", draw_field)
        field.bind("<Button-1>", lambda e: self.entry.focus_set())
        show_hint = lambda *x: (hint.place_forget() if self.query.get() else
                                hint.place(in_=self.entry, x=0, rely=0.5, anchor="w"))
        hint.bind("<Button-1>", lambda e: self.entry.focus_set())
        body = tk.Frame(frame, bg=SURFACE)
        body.pack(fill="both", expand=True, pady=(0, a.px(6)))
        self.canvas = tk.Canvas(body, bg=SURFACE, highlightthickness=0, borderwidth=0,
                                yscrollincrement=self.row_h // 2)
        self.bar = tk.Canvas(body, bg=SURFACE, width=a.px(10), height=1, highlightthickness=0, borderwidth=0)
        self.bar.pack(side="right", fill="y", padx=(0, a.px(3)))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.config(yscrollcommand=lambda f, l: self._draw_bar(float(f), float(l)))
        self.canvas.bind("<Configure>", lambda e: self._draw())
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._pick(self._row_at(e.y)))
        self.bar.bind("<Button-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_drag)
        self.bar.bind("<Configure>", lambda e: self._draw_bar(*self.canvas.yview()))
        for key, step in (("<Down>", 1), ("<Up>", -1), ("<Next>", 10), ("<Prior>", -10)):
            self.entry.bind(key, lambda e, s=step: self._move(s))
        self.entry.bind("<Return>", lambda e: self._pick())
        self.entry.bind("<KP_Enter>", lambda e: self._pick())
        self.entry.bind("<Escape>", lambda e: self.close(refocus=True))
        self.entry.bind("<Tab>", lambda e: self.close(refocus=True))
        self.popup.bind("<Button-1>", self._click_out)
        self.query.trace_add("write", lambda *x: (show_hint(), self._fill()))
        a.search_popup = self
        show_hint()
        self._fill(first=True)
        self._place()
        self._see(self.at, center=True)
        self.opened_at = self.window_at()
        self.entry.bind("<FocusOut>", lambda e: self.box.after(80, self._focus_left))
        try:
            self.prev_grab = self.box.grab_current()   # a dialog's own grab, given back on close
            self.popup.grab_set()             # a click outside reaches the pop-up, which closes
        except tk.TclError:
            pass
        self.entry.focus_force()
        self.entry.icursor("end")

    def _fill(self, first=False):
        """Work out the rows (a name, or None for a heading / the no-match line) and draw them."""
        if self.popup is None:
            return
        matches = self._find(self.query.get())
        cur = self.text()
        self.rows, self.texts, self.tops, self.at = [], [], [], None
        y, last = 0, object()
        for n in matches:
            h = self.head(n) if self.head else None
            if h is not None and h != last:
                self.rows.append(None)
                self.texts.append(h.upper())
                self.tops.append(y)
                y += self.head_h
            last = h
            self.rows.append(n)
            self.texts.append(self.label(n))
            self.tops.append(y)
            y += self.row_h
            if first and self.at is None and self.value(n) == cur:
                self.at = len(self.rows) - 1
        q = self.query.get().strip()
        if self.own and q and not any(self.value(n).lower() == q.lower() for n in matches):
            self.rows.append((q,))            # the user's own text, not a list entry
            self.texts.append(f"Use \u201c{q}\u201d")
            self.tops.append(y)
            y += self.row_h
        elif not matches:
            self.rows.append(None)
            self.texts.append(f"No matches for \u201c{q}\u201d")
            self.tops.append(y)
            y += self.row_h
        self.total = y
        if self.at is None:
            self.at = next((i for i, r in enumerate(self.rows) if r is not None), None)
        self.canvas.yview_moveto(0)
        if first:
            self._draw()
        else:
            self._place()                     # the list shrinks to fit what's left

    def _draw(self):
        c, a = self.canvas, self.app
        if c is None:
            return
        c.delete("all")
        w, cur, pad = max(c.winfo_width(), a.px(200)), self.text(), a.px(6)
        for i, (name, text, top) in enumerate(zip(self.rows, self.texts, self.tops)):
            if name is None:
                if text.startswith("No matches"):
                    c.create_text(a.px(14), top + self.row_h / 2, text=text, anchor="w",
                                  fill=MUTED, font=self.font)
                else:                         # a heading: small muted capitals, a little air above
                    c.create_text(a.px(14), top + self.head_h * 0.62, text=text, anchor="w",
                                  fill=MUTED, font=self.head_font)
                continue
            on = i == self.at
            if on:
                rounded_rect(c, pad, top + a.px(2), w - pad, top + self.row_h - a.px(2), a.px(6),
                             fill=ACCENT, outline="")
            c.create_text(a.px(14), top + self.row_h / 2, text=text, anchor="w",
                          fill=ON_ACCENT if on else TEXT, font=self.font)
            if self._val(name) == cur:        # the current pick
                c.create_text(w - a.px(16), top + self.row_h / 2, text="\u2713", anchor="e",
                              fill=ON_ACCENT if on else ACCENT, font=self.font)
        c.config(scrollregion=(0, 0, w, self.total))

    def _draw_bar(self, first, last):
        b, a = self.bar, self.app
        if b is None:
            return
        b.delete("all")
        if last - first >= 0.999:             # everything fits: no scrollbar
            return
        h, w = b.winfo_height(), b.winfo_width()
        top, bottom = first * h, max(first * h + a.px(24), last * h)
        rounded_rect(b, a.px(2), top + a.px(2), w - a.px(2), bottom - a.px(2), (w - a.px(4)) / 2,
                     fill=MUTED, outline="")

    def _bar_press(self, e):
        first, last = self.canvas.yview()
        h = max(1, self.bar.winfo_height())
        if first * h <= e.y <= last * h:      # on the thumb: drag it
            self._drag_from = (e.y, first)
        else:                                 # on the track: jump there
            self.canvas.yview_moveto(max(0, e.y / h - (last - first) / 2))
            self._drag_from = (e.y, self.canvas.yview()[0])

    def _bar_drag(self, e):
        y0, f0 = getattr(self, "_drag_from", (e.y, 0))
        self.canvas.yview_moveto(f0 + (e.y - y0) / max(1, self.bar.winfo_height()))

    def _row_at(self, y):
        y = self.canvas.canvasy(y)
        for i, top in enumerate(self.tops):
            if top <= y < top + (self.row_h if self.rows[i] is not None else self.head_h):
                return i
        return -1

    def _hover(self, e):
        i = self._row_at(e.y)
        if i != self.at and 0 <= i < len(self.rows) and self.rows[i] is not None:
            self.at = i
            self._draw()
        self.canvas.config(cursor="hand2" if 0 <= i < len(self.rows) and self.rows[i] else "")

    def _place(self):
        box, a = self.box, self.app
        top = box.winfo_toplevel()
        tw, th = top.winfo_width(), top.winfo_height()
        widest = max([self.font.measure(t) for t in self.texts] + [0])
        w = max(box.winfo_width(), min(widest + a.px(64), a.px(640)), a.px(320), self.pop_w)
        w = min(w, tw - a.px(8))
        self.pop_w = w                        # never narrower while typing
        gap = a.px(4)
        bx, by = box.winfo_rootx() - top.winfo_rootx(), box.winfo_rooty() - top.winfo_rooty()
        below, above = th - (by + box.winfo_height() + gap) - gap, by - 2 * gap
        self.popup.update_idletasks()
        extra = self.popup.winfo_reqheight() - self.canvas.winfo_reqheight()   # field + edges
        want = min(self.total, a.px(420))
        if self.up is None:                   # pick a side once: below, unless above has more room
            self.up = want + extra > below and above > below
        room = (above if self.up else below) - extra
        self.canvas.config(height=max(min(want, room), self.row_h), width=w - a.px(16))
        self.popup.update_idletasks()
        h = self.popup.winfo_reqheight()
        y = by - h - gap if self.up else by + box.winfo_height() + gap
        x = max(0, min(bx, tw - w))
        self.popup.place(x=x, y=max(0, y), width=w, height=h)
        self.popup.lift()
        self.popup.update_idletasks()
        self._draw()
        self.placed = time.monotonic()        # resizing the window can drop its focus

    def scroll(self, step):
        self.canvas.yview_scroll(step * 3, "units")

    def _see(self, i, center=False):
        if i is None or self.popup is None or self.total <= 0:
            return
        top = self.tops[i]
        if i > 0 and self.rows[i - 1] is None:
            top = self.tops[i - 1]            # keep the row's heading in view too
        bottom = self.tops[i] + self.row_h
        view = self.canvas.winfo_height()
        y0 = self.canvas.canvasy(0)
        if center:
            self.canvas.yview_moveto(max(0, top - view / 2 + self.row_h) / self.total)
        elif top < y0:
            self.canvas.yview_moveto(top / self.total)
        elif bottom > y0 + view:
            self.canvas.yview_moveto((bottom - view) / self.total)

    def _select(self, i, see=True):
        if not (0 <= i < len(self.rows)) or self.rows[i] is None:
            return
        self.at = i
        self._draw()
        if see:
            self._see(i)

    def _move(self, step):
        i = -1 if self.at is None else self.at
        names = [k for k, r in enumerate(self.rows) if r is not None]
        if names:
            ahead = [k for k in names if (k > i if step > 0 else k < i)]
            if ahead:
                n = min(abs(step), len(ahead))
                i = ahead[n - 1] if step > 0 else ahead[-n]
            self._select(i)
        return "break"

    def _pick(self, i=None):
        if self.popup is None:
            return "break"
        if i is None:
            i = -1 if self.at is None else self.at
        if not (0 <= i < len(self.rows)) or self.rows[i] is None:
            return "break"
        name = self.rows[i]
        self.close(refocus=True)
        self.box.tk.globalsetvar(self.var, self._val(name))
        self.last = self._val(name)
        self.on_pick(name[0] if isinstance(name, tuple) else name)
        self._unselect()
        return "break"

    def _val(self, name):
        return name[0] if isinstance(name, tuple) else self.value(name)

    def window_at(self):
        """Where the box's window is on screen and its size (the pop-up closes when it changes)."""
        top = self.box.winfo_toplevel()
        return top.winfo_rootx(), top.winfo_rooty(), top.winfo_width(), top.winfo_height()

    def _focus_left(self):
        try:
            if self.popup is not None and self.box.focus_get() is None:
                if time.monotonic() - getattr(self, "placed", 0) < 0.5:
                    self.entry.focus_force()  # lost to the pop-up's own resize, not another app
                else:
                    self.close()              # another app has the focus now
        except (tk.TclError, KeyError):
            pass

    def _click_out(self, e):
        w = self.popup.winfo_containing(e.x_root, e.y_root)
        if w is None or str(w).find(str(self.popup)) != 0:
            self.close()

    def _unselect(self):
        try:
            if self.box.winfo_exists():
                self.box.selection_clear()
        except tk.TclError:
            pass

    def close(self, refocus=False):
        if self.popup is not None:
            try:
                self.popup.grab_release()
                self.popup.destroy()
                prev = getattr(self, "prev_grab", None)
                if prev is not None and prev.winfo_exists():
                    prev.grab_set()
            except tk.TclError:
                pass
            self.popup = self.entry = self.canvas = self.bar = None
            if refocus:
                try:
                    self.box.focus_force()        # back from the pop-up's own window
                    self._unselect()
                except tk.TclError:
                    pass
        if getattr(self.app, "search_popup", None) is self:
            self.app.search_popup = None
        return "break"


class HandloadsView:
    """The Handloads tab: every handload of every category in one place, to add, edit,
    duplicate, delete, back up and restore. Each card shows the load's Load Dictionary grade
    (against every load of its cartridge, with that category's dictionary weights and distance)."""
    tab = "hand"
    cat = None

    def __init__(self, app, stage, open_id=None):
        self.app, self.root = app, app.root
        self.open_id, self.cat_on = open_id, "All"
        self.scroll_to_open = open_id is not None
        a = app
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(fill="both", expand=True, padx=a.px(34), pady=(a.px(26), a.px(28)))
        wrap.columnconfigure(0, weight=1)
        a.label(wrap, tool_title("hand"), 17, TEXT, True, bg=BG, anchor="w").grid(row=0, column=0, sticky="w")
        blurb = a.label(wrap, "Your own reloads, from every category. Each one is graded against the "
                              "factory loads of its cartridge, the same as in the Load Dictionary, "
                              "and can go head to head.", 11, MUTED, bg=BG, anchor="w", justify="left")
        blurb.grid(row=1, column=0, sticky="ew", pady=(2, 14))
        blurb.bind("<Configure>", lambda e: blurb.configure(wraplength=max(e.width, 1)))
        bar = tk.Frame(wrap, bg=BG)
        bar.grid(row=2, column=0, sticky="ew")
        a.button(bar, "+  New handload", self._new, "primary").pack(side="left")
        for text, cmd in (("Restore…", self._restore), ("Back up…", self._backup)):
            link = tk.Label(bar, text=text, bg=BG, fg=ACCENT, font=a.f(10, True), cursor="hand2")
            link.pack(side="right", padx=(14, 0))
            link.bind("<Button-1>", lambda e, c=cmd: c())
        self.search_row = tk.Frame(wrap, bg=BG)
        self.search_row.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.q_var = tk.StringVar()
        a.label(self.search_row, "SEARCH (NAME, CARTRIDGE, BULLET OR POWDER)", 8, MUTED, True, bg=BG,
                anchor="w").pack(anchor="w", pady=(0, a.px(5)))
        a.field(self.search_row, ttk.Entry, textvariable=self.q_var, font=a.f(11))[0].pack(fill="x")
        self.q_var.trace_add("write", lambda *_: self.draw())
        self.chip_row = tk.Frame(wrap, bg=BG)
        self.chip_row.grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.list = tk.Frame(wrap, bg=BG)
        self.list.grid(row=5, column=0, sticky="ew")
        self.list.columnconfigure(0, weight=1)
        self.note = tk.Frame(wrap, bg=BG)
        self.note.grid(row=6, column=0, sticky="ew", pady=(14, 0))
        disclaimer(a, self.note, BG)
        self.draw()

    # ---- data -------------------------------------------------------------- #
    def items(self):
        """[(category, handload Load)] of every bullet category."""
        out = []
        for c in CATEGORIES:
            if c.grain_style and not self.app.data[c.title]["error"]:
                out += [(c, it) for it in self.app.hand_loads(c)]
        return out

    def grade(self, cat, item):
        """Its Load Dictionary row: against every load of its cartridge, at the dictionary's distance."""
        app = self.app
        loads = [x for x in app.data[cat.title]["detail"] + app.hand_loads(cat)
                 if x.cartridge == item.cartridge]
        item = next(x for x in loads if x.handload and x.hid == item.hid)
        try:
            dist = float(app.carry.get(cat.title, {}).get("dist", cat.default_distance))
        except (TypeError, ValueError):
            dist = cat.default_distance
        return h2h_rows([(cat, item)], dist, None, app.dict_weights, app.price_for,
                        {(cat.title, item.cartridge): loads})[0]

    # ---- drawing ------------------------------------------------------------ #
    def draw(self):
        a = self.app
        for w in self.chip_row.winfo_children() + self.list.winfo_children():
            w.destroy()
        items = self.items()
        cats = list(dict.fromkeys(c.title for c, _ in items))
        if self.cat_on not in cats:
            self.cat_on = "All"
        if len(cats) > 1:
            for name in ["All"] + cats:
                n = len(items) if name == "All" else sum(c.title == name for c, _ in items)
                chip = a.chip(self.chip_row, name, lambda nm=name: self._pick_cat(nm),
                              on=name == self.cat_on, note=str(n))
                chip.pack(side="left", padx=(0, a.px(6)))
        if items:
            self.search_row.grid()
        else:
            self.search_row.grid_remove()
            card = a.card(self.list, padx=4, pady=4)
            card.grid(row=0, column=0, sticky="ew", pady=(a.px(16), 0))
            box = card.body
            a.label(box, "No handloads yet", 13, TEXT, True).pack(pady=(22, 4))
            a.label(box, "Click “+  New handload” to add your first. It's graded against the "
                         "factory loads of its cartridge.", 10, MUTED).pack(pady=(0, 22), padx=20)
            return a._update_scroll()
        words = self.q_var.get().lower().split()
        shown = [(c, it) for c, it in items
                 if (self.cat_on == "All" or c.title == self.cat_on) and all(
                     w in " ".join([it.label, it.cartridge] + [it.info.get(k, "") for k in (
                         "bullet_maker", "bullet", "powder", "notes")]).lower() for w in words)]
        if not shown:
            a.label(self.list, "No handloads match.", 11, MUTED, bg=BG, anchor="w").grid(
                row=0, column=0, sticky="w", pady=(14, 0))
            return a._update_scroll()
        order = {c.title: i for i, c in enumerate(CATEGORIES)}
        shown.sort(key=lambda p: (order[p[0].title], p[1].cartridge.lower(), p[1].label.lower()))
        row, last, open_card = 0, None, None
        for c, it in shown:
            if (c.title, it.cartridge) != last:
                last = (c.title, it.cartridge)
                head = tk.Frame(self.list, bg=BG)
                head.grid(row=row, column=0, sticky="w", pady=(18, 6))
                a.label(head, it.cartridge, 12, TEXT, True, bg=BG).pack(side="left")
                a.label(head, f"  ·  {c.title}", 10, MUTED, True, bg=BG).pack(side="left")
                row += 1
            card = self._card(c, it)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            if it.hid == self.open_id:
                open_card = card
            row += 1
        a._update_scroll()
        if open_card is not None and self.scroll_to_open:    # opened from the Load Dictionary
            self.scroll_to_open = False
            self.root.update_idletasks()
            total = max(1, a.stage.winfo_reqheight())
            y = open_card.winfo_rooty() - a.stage.winfo_rooty()
            a.canvas.yview_moveto(max(0.0, (y - a.px(80)) / total))

    def _card(self, cat, it):
        a = self.app
        r = self.grade(cat, it)
        is_open = self.open_id == it.hid
        box = a.card(self.list, border=ACCENT if is_open else BORDER, padx=4, pady=4)
        box.configure(cursor="hand2")
        card = box.body
        card.columnconfigure(0, weight=1)
        name = a.label(card, it.load, 12, TEXT, True, anchor="w", justify="left")
        name.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(8, 0))
        clickable = [box, box.canvas, card, name]
        if a.show_grades:
            gbox = tk.Frame(card, bg=SURFACE)
            gbox.grid(row=0, column=1, rowspan=2, sticky="ne", padx=12, pady=(8, 0))
            Badge(gbox, a, r["grade"], 10).pack(anchor="e")
            rk = a.label(gbox, f"#{r['rank']} of {r['peers']}", 9, MUTED)
            rk.pack(anchor="e", pady=(2, 0))
            clickable += [gbox, rk]
        st = r["stats"]
        stats = a.label(card, f"{st['velocity']:.0f} fps    {st['energy']:.0f} ft-lbs    "
                              f"${st['cost']:.2f} a round    at {r['dist']:g} yd", 10, MUTED, anchor="w")
        stats.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 8))
        clickable.append(stats)
        for w in clickable:
            w.bind("<Button-1>", lambda e, h=it.hid: self._toggle(h))
        if is_open:
            self._details(card, cat, it, r)
        return box

    def _details(self, card, cat, it, r):
        a, rec = self.app, it.info
        tk.Frame(card, bg=BORDER, height=1).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12)
        det = tk.Frame(card, bg=SURFACE)
        det.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 0))
        bullet = " ".join(x for x in (rec.get("bullet_maker", ""), rec.get("bullet", "")) if x) or "Bullet"
        parts = [bullet, f"{it.bullet_gr:g} gr"]
        if it.diameter_in:
            parts.append(f"{it.diameter_in:g} in")
        parts.append(f"BC {it.bc_g1:g}")
        lines = [("Bullet", "  ·  ".join(parts)),
                 ("Powder", "  ·  ".join(x for x in (rec.get("powder", ""), f"{it.powder_gr:g} gr") if x)),
                 ("Velocity", f"{it.muzzle_fps:g} fps" + (f" from a {it.barrel_in:g} in barrel"
                                                          if it.barrel_in else ""))]
        if it.purpose:
            lines.append(("Purpose", it.purpose))
        n = 0
        for n, (k, v) in enumerate(lines):
            a.label(det, k, 10, MUTED, anchor="w").grid(row=n, column=0, sticky="nw", padx=(0, 16), pady=2)
            a.label(det, v, 10, TEXT, True, anchor="w").grid(row=n, column=1, sticky="w", pady=2)
        n += 1
        a.label(det, "Cost", 10, MUTED, anchor="w").grid(row=n, column=0, sticky="nw", padx=(0, 16), pady=2)
        get = lambda k: _opt_float((rec.get(k) or "").replace("$", ""))   # older saves kept text as typed
        parts = [("Bullet", get("bullet_cost")), ("Powder", get("powder_gr") / 7000.0 * get("powder_cost_lb")),
                 ("Primer", get("primer_cost")),
                 ("Brass" + (f" (÷{get('brass_reuse'):g} reloads)" if get("brass_reuse") > 1 else ""),
                  get("brass_cost") / max(1.0, get("brass_reuse") or 1))]
        if any(v for _, v in parts):
            cost = tk.Frame(det, bg=SURFACE)
            cost.grid(row=n, column=1, sticky="w", pady=2)
            for i, (k, v) in enumerate(parts):
                a.label(cost, k, 10, TEXT, True).grid(row=i, column=0, sticky="w", padx=(0, 18))
                a.label(cost, f"${v:.2f}", 10, TEXT).grid(row=i, column=1, sticky="e")
            n_parts = len(parts)
            tk.Frame(cost, bg=BORDER, height=1).grid(row=n_parts, column=0, columnspan=2, sticky="ew", pady=2)
            a.label(cost, "Per round", 10, TEXT, True).grid(row=n_parts + 1, column=0, sticky="w")
            a.label(cost, f"${it.default_cost:.2f}", 10, TEXT, True).grid(row=n_parts + 1, column=1, sticky="e")
        else:
            a.label(det, f"${it.default_cost:.2f} a round", 10, TEXT, True, anchor="w").grid(
                row=n, column=1, sticky="w", pady=2)
        if rec.get("notes"):
            n += 1
            a.label(det, "Notes", 10, MUTED, anchor="w").grid(row=n, column=0, sticky="nw", padx=(0, 16), pady=2)
            a.label(det, rec["notes"], 10, TEXT, anchor="w", justify="left", wraplength=a.px(520)).grid(
                row=n, column=1, sticky="w", pady=2)
        if a.show_grades:
            n += 1
            a.label(det, "Grade", 10, MUTED, anchor="w").grid(row=n, column=0, sticky="nw", padx=(0, 16), pady=2)
            a.label(det, f"{r['grade']}  ·  {r['overall']:.0f}, ranks #{r['rank']} of {r['peers']} "
                         f"{it.cartridge} loads in the Load Dictionary", 10, TEXT, anchor="w").grid(
                row=n, column=1, sticky="w", pady=2)
        btns = tk.Frame(card, bg=SURFACE)
        btns.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        small = dict(size=10, padx=14, pady=7)
        a.button(btns, "Edit", lambda: self._edit(it), "primary", **small).pack(side="left")
        a.button(btns, "Duplicate", lambda: self._duplicate(it), **small).pack(side="left", padx=8)
        delete = a.button(btns, "Delete", lambda: self._delete(cat, it), **small)
        delete.text.configure(fg=DANGER)              # the web's red Delete
        delete.pack(side="left")
        links = tk.Frame(card, bg=SURFACE)
        links.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 8))
        key = pick_key(cat, it)
        h2h = (f"In Head to Head ({len(a.h2h)} of {H2H_MAX})  ›" if key in a.h2h else
               f"Head to Head is full ({H2H_MAX})  ›" if len(a.h2h) >= H2H_MAX else "+  Head to Head")
        for text, cmd in (("Open in Load Dictionary  ›", lambda: self._to_dict(cat, it)),
                          (h2h, lambda: self._to_h2h(cat, it))):
            link = tk.Label(links, text=text, bg=SURFACE, fg=ACCENT, font=a.f(10, True), cursor="hand2")
            link.pack(side="left", padx=(0, 20))
            link.bind("<Button-1>", lambda e, c=cmd: c())

    # ---- actions ------------------------------------------------------------ #
    def _pick_cat(self, name):
        self.cat_on = name
        self.draw()

    def _toggle(self, hid):
        self.open_id = None if self.open_id == hid else hid
        self.draw()

    def _new(self):
        open_handload_dialog(self.app, self.root, on_saved=self._saved)

    def _edit(self, it):
        open_handload_dialog(self.app, self.root, dict(it.info), on_saved=self._saved)

    def _saved(self, row):
        self.open_id = row["id"]
        self.q_var.set("")
        self.draw()

    def _duplicate(self, it):
        row = dict(it.info, id=new_handload_id(), name=(it.info.get("name") or it.load) + " (copy)")
        try:
            self.app.save_handload(row)
        except OSError as exc:
            return messagebox.showerror("Couldn't save", f"Could not write {HANDLOAD_FILENAME}:\n{exc}")
        self._saved(row)

    def _delete(self, cat, it):
        if not messagebox.askyesno("Delete handload", f"Delete \"{it.load}\" from your handloads?"):
            return
        try:
            self.app.delete_handload(it.hid)
        except OSError as exc:
            return messagebox.showerror("Couldn't delete", f"Could not write {HANDLOAD_FILENAME}:\n{exc}")
        key = pick_key(cat, it)
        self.app.h2h[:] = [k for k in self.app.h2h if k != key]
        self.open_id = None
        self.draw()

    def _to_dict(self, cat, it):
        """Open the load in its Load Dictionary: its cartridge, the load selected."""
        app = self.app
        app.carry.setdefault(cat.title, {}).update(cart=it.cartridge, purpose="All", source="All")
        app.go(cat, "loads")
        view = app.view
        if isinstance(view, LoadsView) and view.cat is cat:
            view._reload_loads(select=it)

    def _to_h2h(self, cat, it):
        if self.app.add_to_h2h(cat, it) is None:
            return self.app.show_h2h()
        self.draw()

    def _backup(self):
        rows = self.app.hand_rows
        if not rows:
            return messagebox.showinfo("Back up", "You have no handloads to back up yet.")
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Back up handloads", defaultextension=".csv",
            initialfile="my_handloads-backup.csv", filetypes=[("CSV files", "*.csv"), ("All files", "*")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                fh.write(handload_csv_text(rows))
        except OSError as exc:
            return messagebox.showerror("Couldn't back up", f"Could not write {path}:\n{exc}")
        messagebox.showinfo("Backed up", f"{len(rows)} handload{'s' if len(rows) != 1 else ''} saved to\n"
                                         f"{path}\n\nRestore it on any computer or phone with “Restore”.")

    def _restore(self):
        """A file, or a back up pasted from the phone, merged into the saved handloads."""
        a = self.app
        win = tk.Toplevel(self.root)
        win.configure(bg=BG)
        win.title("Restore handloads")
        win.transient(self.root)
        card = a.card(win, padx=4, pady=4)
        card.pack(padx=16, pady=16, fill="both", expand=True)
        body = card.body
        a.label(body, "Open a back up file (or a my_handloads.csv), or paste a back up copied on "
                      "the phone. Handloads you already have are kept; ones in the back up are "
                      "added, or updated if they came from here.", 10, MUTED, anchor="w",
                justify="left", wraplength=a.px(460)).pack(fill="x", padx=18, pady=(16, 10))
        text = tk.Text(body, height=10, width=60, bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                       relief="flat", font=a.f(9))
        text.pack(fill="both", expand=True, padx=18)

        def open_file():
            from tkinter import filedialog
            path = filedialog.askopenfilename(parent=win, title="Open a handload back up",
                                              filetypes=[("CSV files", "*.csv"), ("All files", "*")])
            if not path:
                return
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    data = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                return messagebox.showerror("Couldn't open", str(exc), parent=win)
            text.delete("1.0", "end")
            text.insert("1.0", data)

        def go():
            cats = {c.title for c in CATEGORIES if c.grain_style}
            try:
                rows, add, rep, skip = merge_handload_rows(a.hand_rows, text.get("1.0", "end"), cats)
                write_handload_rows(rows)
            except ValueError as exc:
                return messagebox.showerror("Can't restore", str(exc), parent=win)
            except OSError as exc:
                return messagebox.showerror("Couldn't save", f"Could not write {HANDLOAD_FILENAME}:\n{exc}",
                                            parent=win)
            a.hand_rows = rows
            win.destroy()
            messagebox.showinfo("Restored", f"{add} new, {rep} updated" + (
                f", {skip} skipped (not a rifle, handgun or rimfire handload, or missing figures)"
                if skip else "") + ".")
            self.draw()

        btns = tk.Frame(body, bg=SURFACE)
        btns.pack(fill="x", padx=18, pady=(12, 16))
        a.button(btns, "Restore", go, "primary").pack(side="left")
        a.button(btns, "Open file…", open_file).pack(side="left", padx=8)
        a.button(btns, "Cancel", win.destroy).pack(side="left")
        win.bind("<Escape>", lambda e: win.destroy())
        text.focus_set()


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
        # "Firearm setup for each load" (Zeke, Oct 29 2026): gun weight, barrel length and twist
        # rate boxes under each load, hidden until opened. While hidden (or a box is blank) the
        # load is in its cartridge's typical gun (GUN_LB) with the listed figures
        self.fire_open = False
        self.slots = []                   # [{cat, cart, load, gun, barrel, twist: StringVar, ...}]
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
        a.label(outer, tool_title("h2h"), 17, TEXT, True, bg=BG).grid(
            row=0, column=0, sticky="w", pady=(0, a.px(12)))
        if not self.groups:
            mbox = a.card(outer, padx=4, pady=4)
            mbox.grid(row=1, column=0, sticky="ew")
            msg = mbox.body
            a.label(msg, "No loads found.", 11, TEXT, True, anchor="w").pack(
                anchor="w", padx=18, pady=(16, 4))
            a.label(msg, "Put the loads_*.csv files next to the program to use this tab.",
                    10, MUTED, anchor="w").pack(anchor="w", padx=18, pady=(0, 16))
            return

        box = a.card(outer, padx=18, pady=14)
        box.grid(row=1, column=0, sticky="ew")
        card = box.body
        card.columnconfigure(0, weight=1)
        pad = dict(padx=0)
        a.label(card, "LOADS TO COMPARE · ANY CATEGORY", 8, MUTED, True).grid(
            row=0, column=0, sticky="w", **pad)
        self.slot_box = tk.Frame(card, bg=SURFACE)
        self.slot_box.grid(row=1, column=0, sticky="ew", pady=(6, 0), **pad)
        self.slot_box.columnconfigure(3, weight=1)
        self.add_link = tk.Label(card, text=f"+  Add a load (up to {H2H_MAX})", bg=SURFACE,
                                 fg=ACCENT, font=a.f(10, True), cursor="hand2")
        self.add_link.grid(row=2, column=0, sticky="w", pady=(8, 0), **pad)
        self.add_link.bind("<Button-1>", lambda e: self._add_slot())

        top = tk.Frame(card, bg=SURFACE)
        top.grid(row=3, column=0, sticky="ew", pady=(a.px(12), 0), **pad)
        a.label(top, "DISTANCE (YD)", 8, MUTED, True).grid(row=0, column=0, sticky="w")
        a.field(top, ttk.Entry, textvariable=self.dist_var, font=a.f(12), width=8)[0].grid(
            row=1, column=0, sticky="w", pady=(a.px(5), 0))
        # opens gun weight, barrel length and twist rate boxes under each load
        self.fire_link = tk.Label(top, text="", bg=SURFACE, fg=ACCENT, font=a.f(10, True),
                                  cursor="hand2")
        self.fire_link.grid(row=1, column=1, sticky="w", padx=(24, 0), pady=(4, 0))
        self.fire_link.bind("<Button-1>", lambda e: self._toggle_fire())
        self.fire_note = a.label(card, "", 9, MUTED, anchor="w", justify="left",
                                 wraplength=a.px(760))
        self.fire_note.grid(row=5, column=0, sticky="w", pady=(a.px(8), 0), **pad)
        self.status = a.label(card, "", 10, DANGER, anchor="w")
        self.status.grid(row=4, column=0, sticky="w", **pad)

        self.results = tk.Frame(outer, bg=BG)
        self.results.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.results.columnconfigure(0, weight=1)
        self.footnote = a.label(outer, "", 9, MUTED, bg=BG, anchor="w", justify="left",
                                wraplength=a.px(880))
        self.footnote.grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _add_slot(self, item=None, icat=None):
        # a new row has no cartridge and opens nothing (Zeke: "+ Add a load" used to copy the
        # last row's cartridge and jump into the load box; Oct 29 2026 the first rows too)
        if len(self.slots) >= H2H_MAX:
            return
        a = self.app
        slot = {"cat": tk.StringVar(value=(icat or self.first).title),
                "cart": tk.StringVar(value=item.cartridge if item else ""),
                "load": tk.StringVar(value=""), "gun": tk.StringVar(value=""),
                "barrel": tk.StringVar(value=""), "twist": tk.StringVar(value="")}
        if item is not None:
            slot["load"].set(next(t for t, x in self.choices[(icat.title, item.cartridge)].items()
                                  if x is item))
        elif self.slots:
            slot["cat"].set(self.slots[-1]["cat"].get())
        widest = max([16] + [len(c) for carts in self.cartridges.values() for c in carts])
        slot["num"] = a.label(self.slot_box, "", 11, MUTED, True)
        slot["cart_wrap"], slot["cart_box"] = a.field(self.slot_box, ttk.Combobox,
                                                      textvariable=slot["cart"], font=a.f(11),
                                                      width=widest)
        slot["cart_search"] = LoadSearch(a, slot["cart_box"], list(self.cart_names),
                                         lambda n, s=slot: self._on_cart_search(s, n),
                                         value=lambda n: self.cart_names[n][1],
                                         head=lambda n: title_name(self.cart_names[n][0]),
                                         label=lambda n: self.cart_names[n][1], hint="Cartridge")
        slot["load_wrap"], slot["load_box"] = a.field(self.slot_box, ttk.Combobox,
                                                      textvariable=slot["load"], font=a.f(11),
                                                      width=40)
        slot["search"] = LoadSearch(a, slot["load_box"], [], lambda n, s=slot: self._on_load(s),
                                    hint=lambda s=slot: "Load" if s["cart"].get() else
                                    "Pick a cartridge first")
        # the firearm boxes, on a line of their own under the load: gun (lb), barrel (in), twist
        slot["fire_box"] = fb = tk.Frame(self.slot_box, bg=SURFACE)
        slot["fire_parts"] = {}
        for key, text, unit in (("gun", "Gun", "lb"), ("barrel", "Barrel", "in"),
                                ("twist", "Twist  1 in", "in  (blank: none)")):
            part = tk.Frame(fb, bg=SURFACE)
            a.label(part, text, 9, MUTED, True).pack(side="left", padx=(0, 6))
            a.field(part, ttk.Entry, textvariable=slot[key], font=a.f(11), width=5)[0].pack(side="left")
            hint = a.label(part, unit, 9, MUTED)
            hint.pack(side="left", padx=(6, 0))
            slot["fire_parts"][key] = (part, hint)
            slot[key].trace_add("write", self._schedule)
        slot["x"] = close_button(a, self.slot_box, lambda s=slot: self._remove_slot(s))
        self.slots.append(slot)
        self._fill_loads(slot)
        self._layout_slots()

    def _fill_loads(self, slot):
        # the cartridge pop-up lists every category's cartridges under its heading, the row's
        # category first
        t = slot["cat"].get()
        cs = slot["cart_search"]
        cs.browse = sorted(self.cart_names, key=lambda n: self.cart_names[n][0] != t)
        cs.last = slot["cart"].get()
        names = list(self.choices.get((slot["cat"].get(), slot["cart"].get()), {}))
        slot["load_box"].config(width=max([40] + [min(len(n), 64) for n in names]))
        slot["search"].names = names
        if slot["load"].get() not in names:
            slot["load"].set("")
        slot["search"].show_hint()
        slot["search"].last = slot["load"].get()

    def _on_load(self, slot):
        """A load was picked from the menu or from the search list."""
        slot["search"].last = slot["load"].get()
        self._layout_slots()
        self._changed()

    def _layout_slots(self):
        self.fire_link.config(text=("▾  Hide firearm setup  (blank boxes: the listed figures)" if self.fire_open
                                    else "▸  Firearm setup for each load"))
        # the note of a picked category with barrels (the carbine one names its estimates)
        cats = [self.cats[s["cat"].get()] for s in self.slots if s["cart"].get()]
        note = next((c for c in cats if c.title == "Pistol Caliber Carbine"),
                    next((c for c in cats if c.barrel_in), self.first))
        self.fire_note.config(text=firearm_note(note))
        if self.fire_open:
            self.fire_note.grid()
        else:
            self.fire_note.grid_remove()
        for n, slot in enumerate(self.slots, start=1):
            row = 2 * n - 1
            slot["num"].config(text=f"{n}")
            slot["num"].grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            slot["cart_wrap"].grid(row=row, column=2, sticky="w", pady=3)
            slot["load_wrap"].grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=3)
            if self.fire_open:
                t, cart = slot["cat"].get(), slot["cart"].get()
                c = self.cats[t]
                item = self.choices.get((t, cart), {}).get(slot["load"].get())
                parts = slot["fire_parts"]
                parts["gun"][1].config(text=f"lb  (usual {typical_gun_lb(c, cart):g})"
                                       if cart else "lb")
                parts["barrel"][1].config(text=f"in  (listed {test_barrel(c, item):g})"
                                          if item else "in")
                for key, (part, _) in parts.items():
                    part.pack_forget()
                    if key == "gun" or c.barrel_in:  # shotshells: no barrel length or twist
                        part.pack(side="left", padx=(0, 18))
                slot["fire_box"].grid(row=row + 1, column=2, columnspan=2, sticky="w",
                                      pady=(0, 8))
            else:
                slot["fire_box"].grid_remove()
            slot["x"].grid(row=row, column=6, sticky="w", padx=(4, 0), pady=3)
            if len(self.slots) <= H2H_MIN and not slot["load"].get():
                slot["x"].grid_remove()           # nothing to remove: the 2 rows always stay
        if len(self.slots) >= H2H_MAX:
            self.add_link.grid_remove()
        else:
            self.add_link.grid()

    def _on_cart_search(self, slot, name):
        """A cartridge was picked from the search list, maybe from another category."""
        t, cart = self.cart_names[name]
        slot["cat"].set(t)
        slot["cart"].set(cart)
        self._on_cart(slot)

    def _on_cart(self, slot):
        slot["load"].set("")
        slot["gun"].set("")                       # another cartridge: back to its usual gun
        slot["barrel"].set("")
        slot["twist"].set("")
        self._fill_loads(slot)
        self._layout_slots()
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
        for key in ("num", "cart_wrap", "load_wrap", "fire_box", "x"):
            slot[key].destroy()
        self.slots.remove(slot)
        while len(self.slots) < H2H_MIN:
            self._add_slot()
        self._layout_slots()
        self._changed()

    def _picked_slots(self):
        """The loads chosen so far as (category, load, slot), in slot order. A load can be picked
        twice, to compare it at two barrel lengths or gun weights (Zeke, Oct 29 2026)."""
        out = []
        for slot in self.slots:
            t = slot["cat"].get()
            item = self.choices.get((t, slot["cart"].get()), {}).get(slot["load"].get())
            if item is not None:
                out.append((self.cats[t], item, slot))
        return out

    def _picked(self):
        return [(c, x) for c, x, _ in self._picked_slots()]

    def _toggle_fire(self):
        self.fire_open = not self.fire_open
        self._layout_slots()
        self.refresh()

    def _save_picks(self):
        self.app.h2h[:] = [pick_key(c, x) for c, x in self._picked()]

    def _changed(self):
        self._save_picks()
        self.refresh()

    # ---- state ------------------------------------------------------------ #
    def snapshot(self):
        # by position, like app.h2h (the same load can be there twice)
        slots = [s for _, _, s in self._picked_slots()]
        return dict(dist=self.dist_var.get(), fire_open=self.fire_open,
                    guns=[s["gun"].get() for s in slots],
                    barrels=[s["barrel"].get() for s in slots],
                    twists=[s["twist"].get() for s in slots])

    def _apply_snap(self, snap):
        if "dist" in snap:
            self.dist_var.set(snap["dist"])
        self.fire_open = snap.get("fire_open", self.fire_open)
        for i, (_, _, slot) in enumerate(self._picked_slots()):
            for key in ("gun", "barrel", "twist"):
                saved = snap.get(key + "s", [])
                if i < len(saved):
                    slot[key].set(saved[i])
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
            guns = [None if not self.fire_open or not s["gun"].get().strip()
                    else LoadsView._num(s["gun"], f"Gun weight for {x.label}", 0.5, GUN_LB_MAX)
                    for _, x, s in picks]
            # a blank box (or the boxes hidden, or a shotshell): the listed figures
            barrels = [None if not self.fire_open or not c.barrel_in or not s["barrel"].get().strip()
                       else LoadsView._num(s["barrel"], f"Barrel length for {x.label}", BARREL_MIN,
                                           BARREL_MAX)
                       for c, x, s in picks]
            twists = [None if not self.fire_open or not c.barrel_in or not s["twist"].get().strip()
                      else LoadsView._twist(s["twist"], f"Twist rate for {x.label}")
                      for c, x, s in picks]
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
            "behind it. Prices are estimates: set your own in the Load Dictionary."
            + (" A load with a barrel length has its speed moved from its test barrel to that "
               "length: an estimate." if any(barrels) else "")
            + (" A load with a twist rate is checked for spin stability (Miller's rule, bullet "
               "length estimated); a barely stable bullet loses some BC: an estimate."
               if any(twists) else ""))
        if len(picked) < H2H_MIN:
            self.app.label(self.results, f"Pick at least {H2H_MIN} loads to put them head to head.",
                           11, MUTED, bg=BG, anchor="w").grid(row=0, column=0, sticky="w")
            return self.app.fit_window()
        rows = h2h_rows(picked, dist, guns, self.app.dict_weights, self.app.price_for, self.groups,
                        barrels, twists)
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
        box = a.card(self.results, padx=4, pady=4)
        box.grid(row=0, column=0, sticky="ew")
        card = box.body
        card.columnconfigure(0, weight=0, minsize=self._label_w())
        for c in range(1, n + 1):
            card.columnconfigure(c, weight=1, uniform="load")
        wrap = a.px(max(160, 760 // n))
        setups = h2h_setups(rows)          # a load picked twice: "10.5 in barrel" etc.
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
            if setups[c - 1]:
                a.label(box, setups[c - 1], 9, ACCENT, True, anchor="w").pack(anchor="w")
            if stability_warn(it):
                a.label(box, stability_warn(it), 9, DANGER, True, anchor="w").pack(anchor="w")
        # a thin line between rows, like the web's table (the thicker rule below stands in for
        # the line under the grade rows, and the card's edge for the one under "Best in")
        line = lambda: a.rule(card, r, n + 1)
        if grades:
            line()
        r += 1
        if grades:
            self._cell(card, r, 0, "Overall", 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                box = tk.Frame(card, bg=SURFACE)
                box.grid(row=r, column=c, sticky="w", padx=12, pady=5)
                Badge(box, a, row["grade"], 12).pack(side="left")
                a.label(box, f"{row['overall']:.0f}", 12, TEXT, True).pack(side="left", padx=(8, 0))
            line()
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
            facts.append(("Test barrel", lambda row: barrel_text(row["cat"], row["item"])))
        if any(getattr(row["item"], "sg", 0) for row in rows):
            facts.append(("Spin stability", lambda row: stability_cell(row["item"])))
        facts.append(("Purpose", lambda row: row["item"].purpose or row["item"].group or "—"))
        for name, fn in facts:
            self._cell(card, r, 0, name, 10, MUTED, True)
            for c, row in enumerate(rows, start=1):
                self._cell(card, r, c, fn(row), 10, TEXT)
            line()
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
                    Badge(box, a, grade_relative(row["scores"][key]), 9).pack(
                        side="left", padx=(8, 0))
            line()
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
        a.label(self.results, "DOWNRANGE", 8, MUTED, True,
                bg=BG, anchor="w").grid(row=1, column=0, sticky="w", pady=(16, 6))
        box = a.card(self.results, padx=4, pady=4)
        box.grid(row=2, column=0, sticky="w")
        dr = box.body
        # like the Load Dictionary's ballistic table: a compact table (it doesn't stretch to the
        # window), each load's name over its own right-aligned Velocity and Energy columns, a thin
        # line between loads, and each column marking its own leader
        heads = ("Velocity (fps)", "Energy (ft-lbs)")
        hf, nf = tkfont.Font(font=a.f(10, True)), tkfont.Font(font=a.f(11, True))
        col_w = max([hf.measure(h) for h in heads] + [nf.measure("00,000")])
        pad = a.px(14)
        for c in range(n):
            dr.columnconfigure(3 * c + 1, minsize=1)                     # the line between loads
            for k in (2, 3):
                dr.columnconfigure(3 * c + k, minsize=col_w + 2 * pad, uniform="dr")

        def cell(r, c, text, color=TEXT, bold=False, size=11, py=3):
            a.label(dr, text, size, color, bold, bg=SURFACE, anchor="e").grid(
                row=r, column=c, sticky="nsew", padx=pad, pady=py)

        table = h2h_downrange([(row["cat"], row["item"]) for row in rows])
        last = len(table) + 3
        a.label(dr, "Yards", 10, MUTED, True, bg=SURFACE, anchor="e").grid(
            row=1, column=0, sticky="nsew", padx=pad, pady=(0, 6))
        for c, row in enumerate(rows):
            tk.Frame(dr, bg=BORDER, width=1).grid(row=0, column=3 * c + 1, rowspan=last, sticky="ns")
            # the cartridge in small grey type, then "Load  ·  124 gr" -> the name on one line (the
            # columns widen for it; only a very long name wraps), the weight in small grey type
            name, _, weight = row["item"].label.rpartition("  ·  ")
            head = tk.Frame(dr, bg=SURFACE)
            head.grid(row=0, column=3 * c + 2, columnspan=2, sticky="s", padx=pad, pady=(8, 6))
            a.label(head, row["item"].cartridge, 9, MUTED, True, bg=SURFACE).pack()
            a.label(head, name or weight, 10, HAND_FG if row["item"].handload else TEXT, True,
                    bg=SURFACE, justify="center", wraplength=a.px(420)).pack()
            if name:
                a.label(head, weight, 9, MUTED, bg=SURFACE).pack()
            if setups[c]:
                a.label(head, setups[c], 9, ACCENT, True, bg=SURFACE).pack()
            if stability_warn(row["item"]):
                a.label(head, stability_warn(row["item"]), 9, DANGER, True, bg=SURFACE).pack()
            cell(1,3 * c + 2, heads[0], MUTED, True, 10, (0, 6))
            cell(1, 3 * c + 3, heads[1], MUTED, True, 10, (0, 6))
        tk.Frame(dr, bg=BORDER, height=1).grid(row=2, column=0, columnspan=3 * n + 1, sticky="ew")
        for i, (yd, cells) in enumerate(table, start=3):
            cell(i, 0, f"{yd:g}", TEXT, True)
            live = [x for x in cells if x]
            v_top, e_top = max(v for v, _ in live), max(e for _, e in live)
            for c, x in enumerate(cells):
                if x is None:
                    cell(i, 3 * c + 2, "—", MUTED)
                    cell(i, 3 * c + 3, "—", MUTED)
                    continue
                v, e = x
                vb, eb = v >= v_top - 1e-9, e >= e_top - 1e-9
                cell(i, 3 * c + 2, f"{v:,.0f}", ACCENT if vb else TEXT, vb)
                cell(i, 3 * c + 3, f"{e:,.0f}", ACCENT if eb else TEXT, eb)
            if i < len(table) + 2:
                a.rule(dr, i, 3 * n + 1)                    # a thin line between distances
        a.label(dr, "", 2, bg=SURFACE).grid(row=last, column=0)


def h2h_setups(rows):
    """For a load picked more than once in Head to Head (the same load at two barrel lengths,
    twists or gun weights): what sets each copy apart, "10.5 in barrel  ·  7 lb gun" (only what differs
    between the copies); "" for a load picked once."""
    same = {}
    for r in rows:
        same.setdefault((r["cat"].title, id(base_load(r["item"]))), []).append(r)

    def barrel(r):
        it, c = r["item"], r["cat"]
        return f"{getattr(it, 'at_in', 0) or test_barrel(c, it):g} in barrel" if c.barrel_in else ""

    out = []
    for r in rows:
        copies = same[(r["cat"].title, id(base_load(r["item"])))]
        parts = []
        if len(copies) > 1 and len({barrel(x) for x in copies}) > 1:
            parts.append(barrel(r))
        twist = lambda x: getattr(x["item"], "twist", 0)
        if len(copies) > 1 and len({twist(x) for x in copies}) > 1:
            parts.append(f"1:{twist(r):g} twist" if twist(r) else "no twist set")
        if len(copies) > 1 and len({x["gun"] for x in copies}) > 1:
            parts.append(f"{r['gun']:g} lb gun")
        out.append("  ·  ".join(p for p in parts if p))
    return out


def h2h_keys(cats):
    """The factors shown in Head to Head: every factor that applies to any of the loads."""
    return [k for k in METRICS if any(k in metric_keys(c) for c in cats)]


def h2h_rows(picked, dist, guns, weights_of, price_of, groups, barrels=None, twists=None):
    """Head to Head figures for the picked (category, load) pairs. Each load is graded the way
    its Load Dictionary grades it (against every load of its cartridge, with weights_of(category)),
    at `dist` capped to its category's max. `best` is the set of factors where it leads the picked
    loads and `gap` how far behind the leader it is, in %; factors that don't apply to a load
    (`keys`) are left out. guns: a gun weight per picked load, None (or a None in the list) for
    its cartridge's typical gun (GUN_LB). barrels: a barrel length per picked load (at_barrel:
    the load and every load it is graded against moved to it), None for the listed figures.
    twists: a twist rate per picked load (at_firearm), None for none.
    `groups` maps (category title, cartridge) to its loads; price_of(category, load)."""
    rows, done = [], {}
    for n, (icat, it) in enumerate(picked):
        gun = guns[n] if guns else None
        gun = typical_gun_lb(icat, it.cartridge) if gun is None else gun
        barrel = (barrels[n] if barrels else None) or 0.0
        twist = (twists[n] if twists else None) or 0.0
        key = (icat.title, it.cartridge, gun, barrel, twist)
        d = min(dist, icat.max_distance)
        if key not in done:
            items = [at_firearm(x, icat, barrel, twist) for x in groups[key[:2]]]
            done[key] = {id(base_load(r["item"])): r for r in score_loads(
                items, d, gun,
                weights_of(icat), [price_of(icat, x) for x in items], by_type=not icat.grain_style)}
        rows.append(dict(done[key][id(it)], cat=icat, dist=d, gun=gun, keys=metric_keys(icat),
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
