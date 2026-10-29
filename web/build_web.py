"""Regenerates www/index.html (the phone/web version) from the CSV files.
Run after editing any data/*.csv or web/template.html:   python3 web/build_web.py
"""
import json, os, shutil, sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, "src"))
import csv
import load_lore as c
data = os.path.join(root, "data")
cats = []
for cat in c.CATEGORIES:
    loads, problems = c.load_data(os.path.join(data, cat.filename), cat.grain_style)
    if problems:
        raise SystemExit(f"{cat.filename}: {problems}")
    detail, dprob = c.load_data(os.path.join(data, cat.loads_filename), cat.grain_style)
    if dprob:
        raise SystemExit(f"{cat.loads_filename}: {dprob}")
    cats.append(dict(title=cat.title, blurb=cat.blurb, default_distance=cat.default_distance,
        max_distance=cat.max_distance, default_gun_lb=cat.default_gun_lb, gun_label=cat.gun_label,
        cartridge_label=cat.cartridge_label, payload_row=cat.payload_row,
        payload_col=cat.payload_col, grain_style=cat.grain_style, show_oz=cat.show_oz,
        weights=list(cat.weights), terminal=cat.terminal, step_yd=cat.step_yd,
        zero_yd=cat.zero_yd, sight_in=cat.sight_in, group=cat.group, menu=cat.menu, note=cat.note, barrel_in=cat.barrel_in,
        detail=[dict(cartridge=x.cartridge, load=x.load, bullet_gr=x.bullet_gr, muzzle_fps=x.muzzle_fps,
                     bc_g1=x.bc_g1, powder_gr=x.powder_gr, default_cost=x.default_cost,
                     is_default=x.is_default, source=x.source, group=x.group,
                     diameter_in=x.diameter_in or 0, barrel_in=x.barrel_in, purpose=x.purpose) for x in detail],
        loads=[dict(cartridge=x.cartridge, load=x.load, bullet_gr=x.bullet_gr, muzzle_fps=x.muzzle_fps,
                    bc_g1=x.bc_g1, powder_gr=x.powder_gr, default_cost=x.default_cost,
                    is_default=x.is_default, source=x.source, group=x.group) for x in loads]))
bullets = [dict(maker=r["maker"], name=r["name"], diameter=float(r["diameter_in"]), weight=float(r["weight_gr"]),
               bc=float(r["bc_g1"]), type=r["type"])
           for r in csv.DictReader(open(os.path.join(data, "bullets.csv"), encoding="utf-8-sig"))]
# the public web address, for link previews; change it here if the site moves to its own domain
SITE = "https://loadlore.net/"
# the beta site (Cloudflare Pages, built from next) sets LOADLORE_BETA=<its address>: link previews
# point there, the tab title says (beta), search engines are asked not to list it, and Settings shows
# "beta" + the commit (Cloudflare gives it as CF_PAGES_COMMIT_SHA)
BETA = os.environ.get("LOADLORE_BETA", "")
if BETA and c.APP_VERSION == "dev":
    c.APP_VERSION = ("beta " + os.environ.get("CF_PAGES_COMMIT_SHA", "")[:7]).strip()
tpl = open(os.path.join(here, "template.html"), encoding="utf-8").read()
if BETA:
    SITE = BETA
    tpl = tpl.replace("<title>In Like Flint - Load Lore</title>",
                      '<title>In Like Flint - Load Lore (beta)</title>\n<meta name="robots" content="noindex">', 1)
os.makedirs(os.path.join(here, "www"), exist_ok=True)
with open(os.path.join(here, "www", "index.html"), "w", encoding="utf-8") as f:
    f.write(tpl.replace("__SITE__", SITE).replace("__DATA__", json.dumps({"version": c.APP_VERSION, "beta": bool(BETA), "about": c.ABOUT_TEXT, "repo": c.REPO_PAGE, "themes": c.THEMES, "default_theme": c.DEFAULT_THEME, "group_blurbs": c.GROUP_BLURBS, "cat_tags": c.CAT_TAGS, "renamed": c.RENAMED_CARTRIDGES, "split": c.SPLIT_CARTRIDGES, "moved": c.MOVED_CATEGORIES, "gun_lb": c.GUN_LB, "gun_max": c.GUN_LB_MAX, "barrel": {"n": c.BARREL_N, "revolvers": c.STANDARD_REVOLVERS, "magnums": c.MAGNUM_REVOLVERS, "rimfire": c.RIMFIRE_HANDGUN, "min": c.BARREL_MIN, "max": c.BARREL_MAX}, "categories": cats, "diameters": c.DIAMETERS, "bullets": bullets, "powders": c.POWDERS, "hand_fields": c.HANDLOAD_FIELDS, "hand_note": c.HANDLOAD_NOTE}, ensure_ascii=False)))
shutil.copyfile(os.path.join(root, "assets", "icon.png"), os.path.join(here, "www", "icon.png"))  # browser tab icon
# home-screen icons (scripts/make_icons.py draws them); the manifest's "browser" display keeps
# "Add to Home screen" a plain shortcut: no install prompt
for name in os.listdir(os.path.join(root, "assets", "web")):
    shutil.copyfile(os.path.join(root, "assets", "web", name), os.path.join(here, "www", name))
with open(os.path.join(here, "www", "manifest.webmanifest"), "w", encoding="utf-8") as f:
    json.dump({"name": c.APP_TITLE, "short_name": "Load Lore", "start_url": ".", "display": "browser",
               "background_color": "#0e1014", "theme_color": "#0e1014",
               "icons": [{"src": f"icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (192, 512)]},
              f, indent=1)
print("wrote www/index.html")
