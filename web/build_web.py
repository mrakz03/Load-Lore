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
POWDERS = ["H4350","H4831SC","H1000","Varget","H4895","H335","H322","CFE 223","Benchmark","Lil'Gun","H110","H4198",
  "Titegroup","Longshot","Universal","Clays","HS-6","H380","Retumbo","Superformance","H414","H4227",
  "IMR 4064","IMR 4350","IMR 4895","IMR 4831","IMR 3031","IMR 7828","IMR 4198","IMR 8208 XBR","IMR 4227","IMR 4759",
  "Reloder 7","Reloder 10X","Reloder 15","Reloder 16","Reloder 17","Reloder 19","Reloder 22","Reloder 23","Reloder 25",
  "Reloder 26","Reloder 33","Reloder 50","Unique","Bullseye","Power Pistol","Blue Dot","Red Dot","2400","Green Dot",
  "Herco","Sport Pistol","Winchester 231","Winchester 296","Winchester 748","Winchester 760","Winchester AutoComp",
  "Winchester WSF","Winchester StaBall 6.5","Accurate 2230","Accurate 2460","Accurate 2520","Accurate 4350",
  "Accurate 5744","Accurate No.2","Accurate No.5","Accurate No.7","Accurate No.9","Vihtavuori N140","Vihtavuori N150",
  "Vihtavuori N160","Vihtavuori N165","Vihtavuori N133","Vihtavuori N550","Vihtavuori N320","Vihtavuori N340",
  "Vihtavuori N350","Ramshot Big Boy","Ramshot TAC","Ramshot X-Terminator","Ramshot Enforcer","Ramshot Silhouette",
  "Ramshot Competition","Norma 202","Norma 203B"]
tpl = open(os.path.join(here, "template.html"), encoding="utf-8").read()
os.makedirs(os.path.join(here, "www"), exist_ok=True)
with open(os.path.join(here, "www", "index.html"), "w", encoding="utf-8") as f:
    f.write(tpl.replace("__DATA__", json.dumps({"version": c.APP_VERSION, "about": c.ABOUT_TEXT, "themes": c.THEMES, "default_theme": c.DEFAULT_THEME, "renamed": c.RENAMED_CARTRIDGES, "split": c.SPLIT_CARTRIDGES, "gun_lb": c.GUN_LB, "gun_max": c.GUN_LB_MAX, "categories": cats, "diameters": c.DIAMETERS, "bullets": bullets, "powders": POWDERS}, ensure_ascii=False)))
print("wrote www/index.html")
