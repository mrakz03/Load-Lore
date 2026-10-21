"""Regenerates www/index.html (the phone/web version) from the CSV files.
Run after editing any ammo_*.csv:   python3 build_web.py
"""
import json, os
import cartridge_calculator as c

here = os.path.dirname(os.path.abspath(__file__))
cats = []
for cat in c.CATEGORIES:
    loads, problems = c.load_data(os.path.join(here, cat.filename), cat.grain_style)
    if problems:
        raise SystemExit(f"{cat.filename}: {problems}")
    cats.append(dict(title=cat.title, blurb=cat.blurb, default_distance=cat.default_distance,
        max_distance=cat.max_distance, default_gun_lb=cat.default_gun_lb, gun_label=cat.gun_label,
        cartridge_label=cat.cartridge_label, load_label=cat.load_label, payload_row=cat.payload_row,
        payload_col=cat.payload_col, grain_style=cat.grain_style, show_oz=cat.show_oz,
        weights=list(cat.weights), allow_custom=cat.allow_custom, default_bc=cat.default_bc,
        sort_loads=cat.sort_loads,
        loads=[dict(cartridge=x.cartridge, load=x.load, bullet_gr=x.bullet_gr, muzzle_fps=x.muzzle_fps,
                    bc_g1=x.bc_g1, powder_gr=x.powder_gr, default_cost=x.default_cost,
                    is_default=x.is_default, source=x.source, group=x.group) for x in loads]))
tpl = open(os.path.join(here, "web_template.html"), encoding="utf-8").read()
os.makedirs(os.path.join(here, "www"), exist_ok=True)
with open(os.path.join(here, "www", "index.html"), "w", encoding="utf-8") as f:
    f.write(tpl.replace("__DATA__", json.dumps({"categories": cats}, ensure_ascii=False)))
print("wrote www/index.html")
