"""Regenerates www/index.html (the phone/web version) from the CSV files.
Run after editing any data/*.csv or web/template.html:   python3 web/build_web.py
"""
import json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, "src"))
import csv
import cartridge_calculator as c
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
        zero_yd=cat.zero_yd, sight_in=cat.sight_in,
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
tpl = open(os.path.join(here, "template.html"), encoding="utf-8").read()
os.makedirs(os.path.join(here, "www"), exist_ok=True)
with open(os.path.join(here, "www", "index.html"), "w", encoding="utf-8") as f:
    f.write(tpl.replace("__DATA__", json.dumps({"version": c.APP_VERSION, "about": c.ABOUT_TEXT, "repo": c.REPO_PAGE, "themes": c.THEMES, "default_theme": c.DEFAULT_THEME, "renamed": c.RENAMED_CARTRIDGES, "split": c.SPLIT_CARTRIDGES, "gun_lb": c.GUN_LB, "gun_max": c.GUN_LB_MAX, "categories": cats, "diameters": c.DIAMETERS, "bullets": bullets, "powders": c.POWDERS}, ensure_ascii=False)))
print("wrote www/index.html")
