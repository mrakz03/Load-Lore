#!/usr/bin/env python3
"""
Cartridge Value Calculator - a desktop tool for comparing ammunition by
performance per dollar.

On startup you choose a category (Centerfire Rifle, Handgun, Rimfire Rifle or
Shotgun). Pick a cartridge and load, enter what you pay per round and the
distance you care about, and the program grades velocity, energy, recoil and
cost (S-F) plus an overall score.

Each category has its own data file next to this program:
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
CUSTOM_FIELDS = ["category", "cartridge", "load", "bullet_gr", "muzzle_fps",
                 "bc_g1", "powder_gr", "default_cost"]

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
}
# Default scoring weights: 3 / 3 / 1 / 3  ->  30% / 30% / 10% / 30%
DEFAULT_WEIGHTS = (3, 3, 1, 3)

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


CATEGORIES = (
    Category("Centerfire Rifle", "Hunting, precision, AR/AK and lever-action rounds",
             "ammo_centerfire_rifle.csv", 100, 2000, 8.0, "RIFLE WEIGHT (LB)",
             legacy_filename="ammo_data.csv", default_bc=0.30),
    Category("Handgun", "Pistol and revolver rounds, including .22 LR and .22 WMR",
             "ammo_handgun.csv", 10, 500, 2.0, "HANDGUN WEIGHT (LB)", default_bc=0.15),
    Category("Rimfire Rifle", ".17 and .22 rimfire rifle rounds",
             "ammo_rimfire_rifle.csv", 50, 500, 5.0, "RIFLE WEIGHT (LB)",
             weights=(3, 3, 1, 6), default_bc=0.13),
    Category("Shotgun", "Birdshot, buckshot and slugs",
             "ammo_shotgun.csv", 25, 300, 7.5, "SHOTGUN WEIGHT (LB)",
             cartridge_label="GAUGE", load_label="LOAD", payload_row="Payload",
             payload_col="Payload (gr)", grain_style=False, show_oz=True,
             allow_custom=False, sort_loads=False),
)


def default_weights(cat):
    return dict(zip(METRICS, cat.weights))


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
    "published": "Weight, velocity and ballistic coefficient are manufacturer-published; "
                 "powder charge (used for recoil) is estimated.",
    "partial": "Weight and velocity are manufacturer-published; ballistic coefficient and "
               "powder charge are estimated.",
    "custom": "Your own entry. Anything you left blank was estimated.",
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
    label: str = ""                # text shown in the load dropdown


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
    return os.path.dirname(os.path.abspath(__file__))


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
    )
    if min(item.bullet_gr, item.muzzle_fps, item.bc_g1, item.powder_gr) <= 0:
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
    return {
        "weight": item.bullet_gr,
        "velocity": v,
        "energy": energy_ftlbs(item.bullet_gr, v),
        "recoil": recoil_ftlbs(item.bullet_gr, item.muzzle_fps, item.powder_gr, gun_lb),
        "cost": item.default_cost if cost is None else cost,
    }


def reference_levels(loads, distance_yd, gun_lb):
    """The 'typical' (median) value of each factor across the category's loads."""
    all_stats = [compute_stats(x, distance_yd, gun_lb) for x in loads]
    return {k: statistics.median(s[k] for s in all_stats) for k in METRICS}


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

    CALC_MIN_WIDTH = 700

    def __init__(self, root):
        self.root = root
        families = set(tkfont.families(root))
        self.family = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue",
                                        "Helvetica", "Arial") if f in families), "TkDefaultFont")
        root.configure(bg=BG)
        self._style()

        # load every category's data up front so the picker can show counts
        self.data = {}      # title -> dict(loads=[...], problems=[...], error="")
        custom_rows = read_custom_rows()
        for cat in CATEGORIES:
            self.data[cat.title] = self._load_category(cat, custom_rows)

        self.stage = None
        self.show_launcher()

    # ---- data ------------------------------------------------------------ #
    def _load_category(self, cat, custom_rows):
        names = [cat.filename] + ([cat.legacy_filename] if cat.legacy_filename else [])
        path = next((p for p in (os.path.join(app_dir(), n) for n in names)
                     if os.path.exists(p)), None)
        if path is None:
            return {"loads": [], "problems": [], "error": f"{cat.filename} not found"}
        try:
            loads, problems = load_data(path, cat.grain_style)
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            return {"loads": [], "problems": [], "error": f"Could not read {cat.filename}: {exc}"}
        if not loads:
            return {"loads": [], "problems": problems, "error": f"{cat.filename} has no usable rows"}
        if cat.allow_custom:
            for row in custom_rows:
                if row.get("category") != cat.title:
                    continue
                try:
                    loads.append(load_from_custom_row(row, cat.grain_style))
                except (KeyError, ValueError) as exc:
                    problems.append(f"{CUSTOM_FILENAME} ({row.get('cartridge', '?')}): {exc}")
        return {"loads": loads, "problems": problems, "error": ""}

    # ---- styling --------------------------------------------------------- #
    def f(self, size, bold=False):
        return (self.family, size, "bold" if bold else "normal")

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
                    bordercolor=BORDER, rowheight=28, font=self.f(10))
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

    # ---- window sizing ---------------------------------------------------- #
    def fit_window(self, min_width=0, keep_position=False):
        """Resize the window to fit its content (at least min_width wide) and keep it on screen."""
        r = self.root
        r.update_idletasks()
        x, y = r.winfo_x(), r.winfo_y()
        r.geometry("")                              # drop any old size so we can measure
        r.update_idletasks()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = min(max(r.winfo_reqwidth(), min_width), sw - 40)
        h = min(r.winfo_reqheight(), sh - 90)
        if keep_position:
            x = max(0, min(x, sw - w - 10))
            y = max(0, min(y, sh - h - 70))
        else:
            x = max(0, (sw - w) // 2)
            y = max(10, (sh - h) // 3)
        r.geometry(f"{w}x{h}+{x}+{y}")

    # ---- screens --------------------------------------------------------- #
    def _new_stage(self):
        self.root.unbind("<Return>")
        if self.stage is not None:
            self.stage.destroy()
        self.stage = tk.Frame(self.root, bg=BG)
        self.stage.pack(fill="both", expand=True)
        return self.stage

    def show_launcher(self):
        stage = self._new_stage()
        self.root.title(APP_TITLE)
        self.root.minsize(560, 400)
        wrap = tk.Frame(stage, bg=BG)
        wrap.pack(padx=28, pady=26)
        self.label(wrap, APP_TITLE, 20, TEXT, True, bg=BG).pack(anchor="w")
        self.label(wrap, "Choose a category to get started.", 11, MUTED,
                   bg=BG).pack(anchor="w", pady=(2, 16))
        grid = tk.Frame(wrap, bg=BG)
        grid.pack()
        for i, cat in enumerate(CATEGORIES):
            info = self.data[cat.title]
            if info["error"]:
                caption = "Data file missing" if "not found" in info["error"] else "Data problem"
            else:
                n_loads = len(info["loads"])
                n_carts = len({x.cartridge for x in info["loads"]})
                caption = f"{n_carts} cartridges  ·  {n_loads} loads"
            card = self._card(grid, cat.title, cat.blurb, caption,
                              lambda c=cat: self.open_category(c))
            card.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="nsew")
        self.fit_window()

    def _card(self, parent, title, blurb, caption, command):
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER,
                        width=250, height=130, cursor="hand2")
        card.pack_propagate(False)
        t = self.label(card, title, 15, TEXT, True, anchor="w")
        t.pack(anchor="w", padx=16, pady=(16, 2))
        b = self.label(card, blurb, 10, MUTED, anchor="w", justify="left", wraplength=215)
        b.pack(anchor="w", padx=16)
        c = self.label(card, caption, 9, ACCENT, True, anchor="w")
        c.pack(anchor="w", padx=16, side="bottom", pady=(0, 14))
        widgets = (card, t, b, c)

        def inside(w):
            while w is not None:
                if w is card:
                    return True
                w = w.master
            return False

        def paint(color):
            for w in widgets:
                w.config(bg=color)
            card.config(highlightbackground=ACCENT if color == SURFACE_2 else BORDER)

        for w in widgets:
            w.bind("<Enter>", lambda e: paint(SURFACE_2))
            w.bind("<Leave>", lambda e: None if inside(card.winfo_containing(
                *card.winfo_pointerxy())) else paint(SURFACE))
            w.bind("<Button-1>", lambda e: command())
        return card

    def open_category(self, cat):
        info = self.data[cat.title]
        if info["error"]:
            messagebox.showerror("Can't open this category", info["error"] +
                                 f"\n\nExpected next to the program:\n{app_dir()}")
            return
        if info["problems"]:
            messagebox.showwarning("Some rows were skipped", "\n".join(info["problems"][:15]))
            info["problems"] = []                   # only warn once
        stage = self._new_stage()
        self.root.title(f"{APP_TITLE} — {cat.title}")
        self.root.minsize(self.CALC_MIN_WIDTH, 560)
        self.view = CalculatorView(self, stage, cat, info["loads"])
        self.fit_window(self.CALC_MIN_WIDTH)        # the calculator gets a roomier window


class CalculatorView:
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

        self._build_ui(stage)
        for var in self.weight_vars.values():
            var.trace_add("write", self._refresh_weight_note)
        self._refresh_weight_note()
        self.root.bind("<Return>", lambda e: self.calculate())

    def _regroup(self):
        self.groups = group_by_cartridge(self.loads, self.cat.sort_loads)
        self.cartridges = list(self.groups)

    # ---- layout ---------------------------------------------------------- #
    def _build_ui(self, stage):
        a, cat = self.app, self.cat
        outer = tk.Frame(stage, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        outer.columnconfigure(0, weight=1)

        back = tk.Label(outer, text="‹  All categories", bg=BG, fg=ACCENT,
                        font=a.f(10, True), cursor="hand2")
        back.grid(row=0, column=0, sticky="w")
        back.bind("<Button-1>", lambda e: a.show_launcher())
        a.label(outer, cat.title, 20, TEXT, True, bg=BG).grid(row=1, column=0, sticky="w",
                                                              pady=(6, 0))
        a.label(outer, "Compare loads by performance per dollar.", 11, MUTED,
                bg=BG).grid(row=2, column=0, sticky="w", pady=(2, 16))

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
        for i, key in enumerate(METRICS):
            a.label(self.weights_frame, METRICS[key][0], 10, MUTED).grid(
                row=0, column=i * 2, padx=(0 if i == 0 else 14, 6))
            ttk.Spinbox(self.weights_frame, from_=0, to=10, increment=1, width=3,
                        textvariable=self.weight_vars[key], font=a.f(11)).grid(
                row=0, column=i * 2 + 1)
        self.weight_note = a.label(self.weights_frame, "", 9, TEXT, True)
        self.weight_note.grid(row=1, column=0, columnspan=8, sticky="w", pady=(8, 0))
        a.label(self.weights_frame, "Higher = matters more. 0 ignores that factor.",
                9, MUTED).grid(row=2, column=0, columnspan=8, sticky="w", pady=(2, 0))
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
                                 wraplength=600)
        self.res_title.grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(16, 0))
        self.res_sub = a.label(self.result, "", 10, MUTED, anchor="w")
        self.res_sub.grid(row=1, column=0, columnspan=3, sticky="w", padx=18, pady=(2, 10))

        self.res_values, self.res_badges = {}, {}
        rows = (("weight", cat.payload_row), ("velocity", "Velocity"), ("energy", "Energy"),
                ("recoil", "Recoil"), ("cost", "Cost"))
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

        tk.Frame(self.result, bg=BORDER, height=1).grid(row=7, column=0, columnspan=3,
                                                         sticky="ew", padx=18, pady=(8, 8))
        a.label(self.result, "Overall", 11, MUTED).grid(row=8, column=0, sticky="w", padx=18)
        self.res_overall = a.label(self.result, "", 14, TEXT, True)
        self.res_overall.grid(row=8, column=1, columnspan=2, sticky="e", padx=18)
        self.bar = tk.Canvas(self.result, height=22, bg=SURFACE, highlightthickness=0)
        self.bar.grid(row=9, column=0, columnspan=3, sticky="ew", padx=18, pady=(8, 4))
        self.res_note = a.label(self.result, "", 9, MUTED, anchor="w", justify="left",
                                wraplength=600)
        self.res_note.grid(row=10, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 16))
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
            text = "  ·  ".join(f"{METRICS[k][0]} {100 * vals[k] / total:.0f}%" for k in METRICS)
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
    def calculate(self):
        item = self._selected_load()
        if item is None:
            messagebox.showinfo("Pick a cartridge", "Choose a cartridge and load first.")
            return
        try:
            dist, gun, cost, weights = self._read_inputs()
        except ValueError as exc:
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
        for key, badge in self.res_badges.items():
            bg, fg = GRADE_COLORS[grades[key]]
            badge.config(text=grades[key], bg=bg, fg=fg)
        self.res_overall.config(text=f"{overall_grade}  ·  {overall:.1f}%")

        src = SOURCE_NOTES.get(item.source, DEFAULT_SOURCE_NOTE)
        self.res_note.config(
            text=f"{src} Each factor is scored on a curve against a typical load in this "
                 f"category (a typical load scores {TYPICAL_SCORE:.0f}), so extra speed or "
                 f"energy past a point earns less. Recoil assumes a {gun:g} lb gun.")
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
        load_var, bc_var, powder_var = (tk.StringVar() for _ in range(3))

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
        a.label(more, f"Leave blank to use typical values (BC {cat.default_bc:g}; powder "
                      f"estimated from the speed and weight). Filling these in makes the recoil "
                      f"and long-range numbers more accurate.",
                9, MUTED, anchor="w", justify="left", wraplength=470).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
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
            return dict(category=cat.title, cartridge=cart,
                        load=load_var.get().strip() or "Custom",
                        bullet_gr=f"{gr:g}", muzzle_fps=f"{fps:g}",
                        bc_g1=f"{(bc if bc is not None else cat.default_bc):g}",
                        powder_gr=f"{(powder if powder is not None else estimate_powder(gr, fps)):.1f}",
                        default_cost=f"{cost:.2f}")

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
        a = self.app
        try:
            dist, gun, _, weights = self._read_inputs(need_cost=False)
        except ValueError as exc:
            messagebox.showerror("Check your input", str(exc))
            return
        refs = reference_levels(self.loads, dist, gun)
        rows = []
        for item in self.loads:
            stats = compute_stats(item, dist, gun)
            _, overall = score_stats(stats, refs, weights)
            rows.append((item.cartridge, item.label, round(stats["weight"]), round(stats["velocity"]),
                         round(stats["energy"]), round(stats["recoil"], 1), stats["cost"],
                         round(overall, 1), grade_for(overall)))

        win = tk.Toplevel(self.root)
        win.configure(bg=BG)
        win.title(f"{self.cat.title}: all loads at {dist:g} yards")
        cols = (self.cat.cartridge_label.title(), "Load", self.cat.payload_col, "Velocity (fps)",
                "Energy (ft-lbs)", "Recoil (ft-lbs)", "Cost ($)", "Score (%)", "Grade")
        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=14, pady=(14, 6))
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=min(len(rows), 22))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        load_w = 300 if not self.cat.grain_style else 170
        widths = (130, load_w, 90, 108, 116, 116, 74, 84, 62)
        for col, w in zip(cols, widths):
            tree.column(col, width=w, anchor="w" if col in cols[:2] else "center")
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        sort_state = {"col": None, "desc": True}
        best_first = (cols[2], "Velocity (fps)", "Energy (ft-lbs)", "Score (%)")

        def render(data):
            tree.delete(*tree.get_children())
            for r in data:
                tree.insert("", "end", values=(r[0], r[1], r[2], r[3], r[4], r[5],
                                               f"{r[6]:.2f}", r[7], r[8]))

        def sort_by(index, col):
            if sort_state["col"] == col:
                desc = not sort_state["desc"]
            else:                                  # first click: best-first for each column
                desc = col in best_first
            sort_state.update(col=col, desc=desc)
            render(sorted(rows, key=lambda r: r[index], reverse=desc))

        for i, col in enumerate(cols):
            tree.heading(col, text=col, command=lambda i=i, c=col: sort_by(i, c))
        tk.Label(win, text="Click a heading to sort. Scores use your current weights and each "
                           "load's default price from the data file.",
                 bg=BG, fg=MUTED, font=a.f(9)).pack(pady=(0, 12))
        sort_by(7, "Score (%)")


def main():
    if tk is None:
        sys.exit("Tkinter is not available. On Linux, install it with your package manager "
                 "(for example: sudo apt install python3-tk).")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
