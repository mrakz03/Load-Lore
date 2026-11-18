"""Load Lore's data tables and CSV reader, used by build_web.py to build the web app.

The app itself (scoring, ballistics, every page) is web/template.html; this file holds what
build_web.py hands it as DATA: the categories, themes, gun weights, barrel and twist limits,
product lines, powders, primers, cartridge renames and the handload fields. Python standard
library only. (Until v1.15 these lived in src/load_lore.py, the Windows / Linux desktop app, which is
kept on the desktop branch.)
"""

import csv
import re
from dataclasses import dataclass

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

HANDLOAD_FIELDS = ["id", "category", "cartridge", "name", "bullet_maker", "bullet", "bullet_gr",
                   "diameter_in", "bc_g1", "powder", "powder_gr", "muzzle_fps", "barrel_in",
                   "purpose", "cost", "bullet_cost", "powder_cost_lb", "primer_cost",
                   "brass_cost", "brass_reuse", "notes", "col_in", "primer"]

# Handload powders by maker (Zeke, Nov 16 2026: the web form lists them under brand headings).
# Names are what saved handloads hold, so keep an old name when a list changes.
POWDER_BRANDS = {
    "Accurate": ["Accurate No.2", "Accurate No.5", "Accurate No.7", "Accurate No.9", "Accurate 1680",
                 "Accurate 2015", "Accurate 2200", "Accurate 2230", "Accurate 2460", "Accurate 2495",
                 "Accurate 2520", "Accurate 2700", "Accurate 3100", "Accurate 4064", "Accurate 4350",
                 "Accurate 5744", "Accurate LT-30", "Accurate LT-32", "Accurate MagPro"],
    "Alliant": ["2400", "20/28", "300-MP", "American Select", "AR-Comp", "BE-86", "Blue Dot", "Bullseye",
                "Clay Dot", "e3", "Extra-Lite", "Green Dot", "Herco", "Power Pistol", "Power Pro 2000-MR",
                "Power Pro 4000-MR", "Power Pro Varmint", "Promo", "Red Dot", "Reloder 7", "Reloder 10X",
                "Reloder 15", "Reloder TS 15.5", "Reloder 16", "Reloder 17", "Reloder 19", "Reloder 22",
                "Reloder 23", "Reloder 25", "Reloder 26", "Reloder 33", "Reloder 50", "Sport Pistol",
                "Steel", "Unique"],
    "Hodgdon": ["Benchmark", "CFE 223", "CFE BLK", "CFE Pistol", "Clays", "H110", "H322", "H335",
                "H380", "H414", "H1000", "H4198", "H4227", "H4350", "H4831", "H4831SC", "H4895",
                "H50BMG", "HP-38", "HS-6", "Hybrid 100V", "International", "LEVERevolution", "Lil'Gun",
                "Longshot", "Retumbo", "Superformance", "Titegroup", "Universal", "US 869", "Varget"],
    "IMR": ["IMR 3031", "IMR 4007 SSC", "IMR 4064", "IMR 4166", "IMR 4198", "IMR 4227", "IMR 4320",
            "IMR 4350", "IMR 4451", "IMR 4756", "IMR 4759", "IMR 4831", "IMR 4895", "IMR 4955",
            "IMR 7625", "IMR 700-X", "IMR 7828", "IMR 7977", "IMR 800-X", "IMR 8133", "IMR 8208 XBR",
            "IMR Blue", "IMR Red", "IMR Target", "IMR Unequal", "Trail Boss"],
    "Norma": ["Norma 200", "Norma 201", "Norma 202", "Norma 203B", "Norma 204", "Norma 217",
              "Norma MRP", "Norma URP"],
    "Ramshot": ["Ramshot Big Boy", "Ramshot Competition", "Ramshot Enforcer", "Ramshot Hunter",
                "Ramshot LRT", "Ramshot Magnum", "Ramshot Silhouette", "Ramshot TAC", "Ramshot True Blue",
                "Ramshot X-Terminator", "Ramshot Zip"],
    "Vihtavuori": ["Vihtavuori 3N37", "Vihtavuori 3N38", "Vihtavuori 20N29", "Vihtavuori 24N41",
                   "Vihtavuori N105", "Vihtavuori N110", "Vihtavuori N120", "Vihtavuori N130",
                   "Vihtavuori N133", "Vihtavuori N135", "Vihtavuori N140", "Vihtavuori N150",
                   "Vihtavuori N160", "Vihtavuori N165", "Vihtavuori N170", "Vihtavuori N310", "Vihtavuori N320",
                   "Vihtavuori N330", "Vihtavuori N340", "Vihtavuori N350", "Vihtavuori N540", "Vihtavuori N550",
                   "Vihtavuori N555", "Vihtavuori N560", "Vihtavuori N565", "Vihtavuori N570"],
    "Winchester": ["Winchester 231", "Winchester 244", "Winchester 296", "Winchester 572", "Winchester 748",
                   "Winchester 760", "Winchester AutoComp", "Winchester StaBall 6.5", "Winchester StaBall HD",
                   "Winchester StaBall Match", "Winchester Super Handicap", "Winchester Super-Target",
                   "Winchester WSF", "Winchester WST"],
}

POWDERS = [p for b in sorted(POWDER_BRANDS, key=str.lower) for p in POWDER_BRANDS[b]]

# Handload primers by maker (Zeke, Nov 17 2026: the web form's Primer box lists them under maker headings
# like the powders). Names are what saved handloads hold; another primer can be typed in.
PRIMER_BRANDS = {
    "CCI": ["CCI 400 Small Rifle", "CCI 41 Small Rifle Military", "CCI 450 Small Rifle Magnum",
            "CCI BR4 Small Rifle Bench Rest", "CCI 200 Large Rifle", "CCI 250 Large Rifle Magnum",
            "CCI BR2 Large Rifle Bench Rest", "CCI 34 Large Rifle Military", "CCI 35 .50 BMG Military",
            "CCI 500 Small Pistol", "CCI 550 Small Pistol Magnum", "CCI 300 Large Pistol",
            "CCI 350 Large Pistol Magnum"],
    "Federal": ["Federal 205 Small Rifle", "Federal 205M Small Rifle Match", "Federal 205MAR Small Rifle AR Match",
                "Federal 210 Large Rifle", "Federal 210M Large Rifle Match", "Federal 215 Large Rifle Magnum",
                "Federal 215M Large Rifle Magnum Match", "Federal 100 Small Pistol",
                "Federal 100M Small Pistol Match", "Federal 200 Small Pistol Magnum", "Federal 150 Large Pistol",
                "Federal 155 Large Pistol Magnum"],
    "Fiocchi": ["Fiocchi Small Rifle", "Fiocchi Small Rifle Magnum", "Fiocchi Large Rifle",
                "Fiocchi Small Pistol", "Fiocchi Large Pistol"],
    "Murom": ["Murom KVB-223 Small Rifle", "Murom KVB-7 Large Rifle"],
    "Remington": ["Remington 6 1/2 Small Rifle", "Remington 7 1/2 Small Rifle Bench Rest",
                  "Remington 9 1/2 Large Rifle", "Remington 9 1/2M Large Rifle Magnum",
                  "Remington 1 1/2 Small Pistol", "Remington 5 1/2 Small Pistol Magnum",
                  "Remington 2 1/2 Large Pistol"],
    "Winchester": ["Winchester WSR Small Rifle", "Winchester WLR Large Rifle", "Winchester WLRM Large Rifle Magnum",
                   "Winchester WSP Small Pistol", "Winchester WSPM Small Pistol Magnum", "Winchester WLP Large Pistol"],
}

PRIMERS = [p for b in sorted(PRIMER_BRANDS, key=str.lower) for p in PRIMER_BRANDS[b]]

# Default scoring weights: velocity / energy / recoil / cost / Taylor KO / HITS.
# 3 / 3 / 1 / 3 / 3 / 3 -> about 19% each, recoil 6%. Shotshells have no Taylor KO / HITS
# (no bullet diameter), so the Shotgun category keeps those two at 0.
DEFAULT_WEIGHTS = (3, 3, 1, 3, 3, 3)

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

CATEGORIES = (
    Category("Centerfire Rifle", "Hunting, precision and military rounds",
             "ammo_centerfire_rifle.csv", 0, 2000, 8.0, "RIFLE WEIGHT (LB)",
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

# Product lines for "Sort: brand (product line)" (Zeke, Oct 31 2026): each brand's lines as they
# start a load's name after the brand. The longest match wins ("Premium Gold Medal" before
# "Premium"); "A=B" files A under line B (the same product named two ways). A load matching none
# goes with its brand's other unlined loads, after the named lines. build_web.py passes the
# prefixes to the web as DATA.lines.
PRODUCT_LINES = {
    "Barnes": ["VOR-TX", "Precision Match", "Pioneer", "Suppressor Series", "Harvest Collection"],
    "Berger": ["Hybrid Target", "Hybrid OTM Tactical"],
    "Black Hills": ["Gold", "HoneyBadger"],
    "Buffalo Bore": ["Anti-Personnel", "Outdoorsman", "Supercharged", "Premium Supercharged",
                     "Dangerous Game", "Tactical", "Penetrator", "Deer Grenade", "Short Barrel",
                     "Low Recoil", "Lower Recoil", "Barnes", "Hard Cast", "Heavy"],
    "CCI": ["Blazer", "Blazer Brass", "Blazer Aluminum", "Mini-Mag", "Maxi-Mag", "Maxi Mag=Maxi-Mag",
            "Stinger", "Velocitor", "Clean-22", "Quiet-22", "Suppressor", "Standard Velocity",
            "Green Tag", "CB", "Pistol Match", "Uppercut", "AR Tactical", "Hunter Series", "VNT", "A17"],
    "ELEY": ["tenex", "match", "team", "club", "contact", "force", "ultra", "biathlon", "sport/target",
             "subsonic", "high velocity", "semi-auto benchrest", "bullseye"],
    "Federal": ["+Peak", "Premium +Peak=+Peak", "All-American", "American Eagle", "Black Cloud",
                "AutoMatch", "Champion", "Force X2", "Fusion", "Gold Medal", "Premium Gold Medal=Gold Medal",
                "Game Load", "HammerDown", "Premium Hammerdown=HammerDown", "Hevi-Bismuth",
                "Master Class", "Military Grade", "Punch", "Personal Defense Punch=Punch", "Personal Defense",
                "Power-Shok", "Raptor", "Shorty", "Speed-Shok", "Subsonic", "Syntech", "Top Gun",
                "Train+Protect", "Training", "Ultra Steel", "Upland Steel", "Varmint & Predator", "Premium",
                "Premium Big Game", "Premium Personal Defense HST",
                "Premium Personal Defense Hydra-Shok", "Premium Hunting Handgun", "Premium Safari",
                "Premium Heavyweight TSS", "Premium High Over All", "Premium Prairie Storm",
                "Premium Upland", "Premium Grand Slam", "Premium 3rd Degree", "Premium Buckshot",
                "Premium Hi-Bird", "Premium Freight Train", "Premium Terminal Ascent",
                "Premium Trophy Bonded", "Premium Trophy Copper", "Premium Swift A-Frame",
                "Premium TruBall", "Premium Barnes", "Premium Berger", "Premium Varmint",
                "Premium Paper Flyer"],
    "Fiocchi": ["Backwoods Hunter", "CovertX", "Cowboy Action", "Crusher", "Super Crusher",
                "Defense Dynamics", "Field Dynamics", "Flyway", "Golden Goose", "Golden Pheasant",
                "Golden Turkey", "Golden Waterfowl", "Heritage", "Hyperformance", "Little Rino",
                "Paper Little Rino", "White Rino", "Range Dynamics", "Shooting Dynamics", "VIP",
                "Steel Target", "Arkansas Steel"],
    "Hornady": ["American Gunner", "American Whitetail", "BLACK", "Backcountry Defense",
                "Critical Defense", "Critical Duty", "Custom", "Dangerous Game", "ELD Match",
                "Match", "ELD-VT", "Frontier", "Handgun Hunter", "LEVERevolution", "Outfitter",
                "Precision Hunter", "Subsonic", "Superformance", "V-MAX"],
    "IMI": ["Razor Core"],
    "Lapua": ["Mega", "Naturalis", "Scenar", "Scenar-L"],
    "Norma": ["Bondstrike", "Golden Target", "Oryx", "Tipstrike", "Whitetail"],
    "Nosler": ["Trophy Grade", "Defense", "E-Tip", "Match Grade", "Whitetail Country"],
    "PMC": ["Bronze", "X-TAC"],
    "PPU": ["GROM", "Z-GROM", "Match"],
    "Remington": ["Core-Lokt", "Core-Lokt Tipped", "Core-Lokt Copper", "Duck Club", "Express",
                  "Golden Saber", "Gun Club", "HTP", "Hypersonic Steel", "Nitro 27", "Nitro Magnum",
                  "Nitro Pigeon", "Nitro Turkey", "Nitro-Steel", "Performance Wheelgun", "Premier",
                  "Premier AccuTip", "Premier STS", "Premier TSS", "Premier Swift Scirocco",
                  "Premier MatchKing", "Premier Nitro", "Premier Royal Flush", "Slugger", "UMC",
                  "Ultimate Defense", "Managed Recoil", "Managed-Recoil=Managed Recoil", "Game Loads", "Pheasant Loads",
                  "Heavy Dove", "Final Strut"],
    "SIG Sauer": ["Elite", "Elite V-Crown", "Elite Ball", "Elite Match", "365", "Marksman",
                  "Platinum Hunter", "Legion", "ROSE", "Match Elite"],
    "Sellier & Bellot": ["XRG Defense", "eXergy", "Sierra GameKing", "Nontox", "HPBT Match"],
    "Speer": ["Gold Dot", "Lawman"],
    "Underwood": ["Xtreme Defender", "Xtreme Hunter", "Xtreme Penetrator"],
    "Winchester": ["AA", "American Lever", "Ballistic Silvertip", "Big Bore", "Copper Impact",
                   "Deer Season", "Defender", "Double-X", "Drylok", "Expedition Big Game",
                   "Last Call", "Longbeard", "Match", "Power-Point", "Power Max", "Silvertip",
                   "Super Clean", "Super Pheasant", "Super Suppressed", "Super Target", "Super-X",
                   "Supreme", "USA", "USA Ready", "USA Forged", "USA Valor", "USA White",
                   "Varmint", "Varmint-X", "Wildcat", "Win1911", "WinClean", "Xpert", "Bismuth"],
}

# (lowercase prefix, line it files under), longest prefix first
LINE_PREFIXES = sorted(
    ((f"{b} {e.split('=')[0]}".lower(), f"{b} {e.split('=')[-1]}".lower())
     for b, lines in PRODUCT_LINES.items() for e in lines),
    key=lambda p: -len(p[0]))

# Color themes (passed to the web version by build_web.py). "side" is the web
# sidebar / bottom bar; "scheme" tells the browser whether form controls should be light or dark.
# Optional: "best" colours Head to Head winners (else the accent; Graphite: gold, its grey accent
# read like plain text, Zeke Oct 31 2026).
THEMES = {
    "Classic": dict(bg="#0e1014", surface="#171a21", surface_2="#222732", border="#2d333f",
                    text="#e8eaee", muted="#8a93a3", accent="#4c8dff", accent_hover="#6aa0ff",
                    on_accent="#ffffff", side="#12151b", danger="#e5534b", hand="#5fd1b4", scheme="dark"),
    "Light": dict(bg="#f3f5f8", surface="#ffffff", surface_2="#e9edf3", border="#d3d9e2",
                  text="#161b24", muted="#5b6576", accent="#2563eb", accent_hover="#3b82f6",
                  on_accent="#ffffff", side="#ffffff", danger="#c62828", hand="#0f8a6c", scheme="light"),
    "Graphite": dict(bg="#121212", surface="#1c1c1c", surface_2="#282828", border="#383838",
                     text="#ededed", muted="#9e9e9e", accent="#d4d4d4", accent_hover="#ffffff",
                     on_accent="#121212", side="#171717", danger="#ef6b62", hand="#9be0c9", scheme="dark",
                     best="#f2c94c"),
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

# Typical gun weight (lb, loaded, scoped rifles) for cartridges far from their category's default:
# recoil is worked out for this weight unless you enter your own. A .50 BMG in the rifle default's
# 8 lb read 340+ ft-lbs; in its usual ~30 lb rifle it is about 95 (no muzzle brake).
GUN_LB = {     # per category: the same cartridge can be in a rifle and a handgun (.44 Magnum)
    "Centerfire Rifle": {
        ".50 BMG": 30.0, ".338 Lapua Magnum": 15.0, ".338 Norma Magnum": 15.0,
        ".300 Norma Magnum": 13.0, ".416 Remington Magnum": 10.0,
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

# The longest barrel each cartridge is sold with from the factory (Zeke, Oct 29 2026): the barrel
# box goes no further, since the speed estimate is a stretch past real barrels. Rounded up from
# current and classic production guns (heavy varmint / precision rifles, single-shot pistols such
# as the S&W 460XVR 14 in, lever guns such as the Rossi R92 24 in, military rifles such as the
# Swedish M96 29 in); a cartridge not listed takes its category's (BARREL_MAX_CAT).
BARREL_MAX_CAT = {"Centerfire Rifle": 28.0, "Rimfire Rifle": 24.0, "Handgun": 10.0,
                  "Pistol Caliber Carbine": 20.0}

BARREL_MAX_IN = {
    "Centerfire Rifle": {
        ".204 Ruger": 26, ".22 ARC": 24, ".22 Creedmoor": 26, ".22 Hornet": 24,
        ".22-250 Remington": 26, ".220 Swift": 26, ".222 Remington": 24, ".223 Remington": 26,
        ".224 Valkyrie": 24, ".243 Winchester": 26, ".25 Creedmoor": 24, ".25-06 Remington": 26,
        ".25-35 Winchester": 26, ".250 Savage": 24, ".257 Roberts": 24, ".260 Remington": 26,
        ".270 WSM": 24, ".270 Winchester": 26, ".277 Fury": 20, ".28 Nosler": 26,
        ".280 Remington": 24, ".30 Carbine": 18, ".30 Thompson/Center": 24,
        ".30-06 Springfield": 26, ".30-30 Winchester": 26, ".30-40 Krag": 30, ".300 Blackout": 20,
        ".300 Norma Magnum": 30, ".300 PRC": 26, ".300 Remington Ultra Mag": 26, ".300 Savage": 24,
        ".300 WSM": 26, ".300 Weatherby Magnum": 28, ".300 Winchester Magnum": 26,
        ".303 British": 26, ".308 Winchester": 26, ".32 Winchester Special": 26, ".32-40 Winchester": 30, ".338 ARC": 20, ".338 Federal": 24,
        ".338 Lapua Magnum": 30, ".338 Norma Magnum": 30, ".338 Winchester Magnum": 26,
        ".348 Winchester": 24, ".35 Remington": 22,
        ".35 Whelen": 24, ".350 Legend": 22, ".358 Winchester": 22, ".360 Buckhammer": 22,
        ".375 H&H Magnum": 26, ".375 Ruger": 24, ".38-55 Winchester": 28, ".400 Legend": 22,
        ".416 Remington Magnum": 24,
        ".444 Marlin": 24, ".45-70 Government": 34, ".450 Bushmaster": 22, ".458 Lott": 24,
        ".458 Winchester Magnum": 24, ".50 BMG": 36, "5.45x39mm": 20, "5.56x45mm NATO": 24,
        "6.5 Creedmoor": 28, "6.5 Grendel": 24, "6.5 PRC": 26, "6.5x55mm Swedish": 30,
        "6.8 Western": 24, "6.8mm SPC": 20, "6mm ARC": 24, "6mm Creedmoor": 28,
        "6mm Remington": 24, "7.62x39mm": 20, "7.62x51mm NATO": 26, "7.62x54mmR": 31,
        "7mm PRC": 26, "7mm Remington Magnum": 26, "7mm STW": 26, "7mm WSM": 24,
        "7mm-08 Remington": 24, "7x57mm Mauser": 30, "8x57mm Mauser": 30, "9.3x62mm": 24},
    "Rimfire Rifle": {".17 HMR": 24, ".17 Mach 2": 22, ".17 WSM": 24, ".22 LR": 28,
                      ".22 Long": 24, ".22 Short": 24, ".22 WMR": 24},
    "Handgun": {
        ".22 LR": 10, ".22 WMR": 10, ".25 ACP": 3, "30 Super Carry": 5, ".45 GAP": 5, ".32 ACP": 4, ".32 H&R Magnum": 7,
        ".32 S&W Long": 6, ".327 Federal Magnum": 7.5, ".357 Magnum": 10, ".357 SIG": 6,
        ".38 Special": 8.5, ".38 Super": 6, ".380 ACP": 4.5, ".40 S&W": 6, ".41 Magnum": 10.5,
        ".44 Magnum": 10.6, ".44 Special": 7.5, ".44-40 Winchester": 7.5, ".45 ACP": 6,
        ".45 Colt": 7.5, ".454 Casull": 10, ".460 S&W Magnum": 14, ".480 Ruger": 10,
        ".50 AE": 10, ".500 S&W Magnum": 10.5, "10mm Auto": 6.5, "4.6x30mm": 7,
        "5.7x28mm": 5, "7.62x25mm Tokarev": 10, "9mm Luger": 6, "9x18mm Makarov": 4},
    "Pistol Caliber Carbine": {
        ".327 Federal Magnum": 20, ".357 Magnum": 24, ".38 Special": 24, ".40 S&W": 17.5,
        ".41 Magnum": 20, ".44 Magnum": 24, ".44 Special": 24, ".44-40 Winchester": 24,
        ".45 ACP": 18, ".45 Colt": 24, ".454 Casull": 20, "10mm Auto": 17.5, "5.7x28mm": 16,
        "9mm Luger": 18},
}

def longest_test_barrels(loads):
    """{cartridge: the longest test barrel its loads list}: makers test some short-barrel
    cartridges (7.62x39mm, .350 Legend) in 24 in barrels no rifle is sold with."""
    out = {}
    for x in loads:
        if x.barrel_in and not x.handload:
            out[x.cartridge] = max(out.get(x.cartridge, 0.0), x.barrel_in)
    return out

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

def firearm_note(cat):
    """What the "Firearm setup" settings change, and that the listed figures are the makers'
    (web: DATA.fire_notes). Kept short (Zeke, Oct 31 2026)."""
    if not cat.barrel_in:
        return "Velocity and energy are the makers' figures. Recoil uses this gun weight."
    return (("Listed figures are the makers' or reviewers' chronograph tests; loads marked (est.) "
             "are our estimates" if cat.title == "Pistol Caliber Carbine"
             else "Listed figures are the makers', from their test barrels")
            + ". Recoil uses this gun weight. Your own barrel or twist makes the figures "
            "estimates; twist only checks that the bullet spins fast enough to fly straight.")

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
    ".338 Norma Magnum": 0.338,
    ".300 Norma Magnum": 0.308,
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
    ".360 Buckhammer": 0.358,
    ".32 Winchester Special": 0.321,
    "7x57mm Mauser": 0.284,
    ".338 Federal": 0.338,
    "30 Super Carry": 0.312,
    ".45 GAP": 0.451,
    ".400 Legend": 0.400,
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

# cartridges that left a category (Oct 28 2026: .357 / .44 Magnum lever-gun loads went from
# Centerfire Rifle to Pistol Caliber Carbine): saved handloads and prices follow them
MOVED_CATEGORIES = {"Centerfire Rifle|.357 Magnum": "Pistol Caliber Carbine",
                    "Centerfire Rifle|.44 Magnum": "Pistol Caliber Carbine"}

# ---- the GitHub repo (Settings > Source code) ---- #
UPDATE_REPO = "mrakz03/Load-Lore"

REPO_PAGE = f"https://github.com/{UPDATE_REPO}"      # Settings > Source code (web too)
