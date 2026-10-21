# Cartridge Calculator

Grades ammo S–F on velocity, energy, recoil, cost (plus Taylor KO and HITS, weight 0 by default).
Desktop app: src/cartridge_calculator.py (Tkinter, stdlib only). Phone/web: web/template.html,
built by `python3 web/build_web.py` into web/www (Capacitor wraps it as an APK in CI).

## Rules
- Desktop and web scoring must stay in parity (same formulas, same data).
- Data lives in data/*.csv. After editing any CSV or the template, rebuild the web version.
- Compare Cartridges uses data/ammo_*.csv: generic loads, no brand names. Compare Loads uses
  data/loads_*.csv: every load name starts with its brand (Federal, Hornady, SIG Sauer...).
  Generic rows never go in loads_*.csv, branded rows never in ammo_*.csv.
  ammo_*.csv names are bullet types only (Soft Point, Polymer Tip, Match BTHP, FMJ, JHP, Solid,
  Copper (lead-free)...), no product lines; it covers the common bases per cartridge, not every load.
- Compare Cartridges grades on an absolute curve; Compare Loads grades relative to the
  same cartridge and purpose (median/MAD, centre 70).
- Handloads: my_handloads.csv (desktop) / localStorage (web). Never commit user files
  (my_calibers.csv, my_handloads.csv, settings.json).
- bullets.csv BCs are approximate; load figures are estimates; no safety validation of reloads.
- Metric cartridges are named with "mm" (7.62x51mm NATO, 7.62x54mmR). When renaming a
  cartridge, add old -> new to RENAMED_CARTRIDGES so users' saved files keep matching.
- Colour themes live in THEMES (cartridge_calculator.py); build_web.py passes the same table to
  the web version. Classic is the default and the original look. Use the palette globals
  (BG, SURFACE, TEXT, ACCENT, ON_ACCENT, DANGER, HAND_FG...) / CSS variables, never hard-coded colours.
- Desktop UI sizes come from measured text (App.fit_columns, _sidebar_width), not fixed pixel
  counts: fonts are in points and grow with screen DPI, so fixed widths cut text off on HiDPI.

## Release
git tag vX.Y && git push origin vX.Y  → GitHub Actions builds Windows (Setup.exe + zip), Linux
(tar with install.sh), Android (APK). Pull main first so the tag lands on the latest commit.
- APP_VERSION in cartridge_calculator.py stays "dev" in the repo; CI sets it from the tag.
- Installers upgrade in place and clear old shipped data (ammo_*, loads_*, bullets.csv) first.
- APK updates install over the old app only once the ANDROID_DEBUG_KEYSTORE secret is set
  (see README); until then testers must uninstall the old APK first.

## Testing
- Desktop: python3.12 has Tk here (the default python3 doesn't); drive App headlessly under
  xvfb-run, patching messagebox so popups don't block. Try `tk scaling 2.0` for HiDPI.
- Web: Playwright from /opt/node-tools/node_modules against web/www/index.html.
- Parity: compare score_stats/relative_scores with the web's scoreStats/relativeScores per load.

## Data notes
- No loads were ever deleted (checked against the user's older load files, Oct 2026). The
  cartridges added with the reorganize commit (e84117b) came almost entirely from Hornady's
  catalogue.
- Oct 2026: 241 loads added for those cartridges from the 2026 Federal, Winchester, Remington,
  Fiocchi, PMC and CCI catalogs (user-supplied PDFs, not in the repo), plus a few Barnes, Nosler,
  Buffalo Bore, Sellier & Bellot and PPU loads from retailer listings. Every added row and its
  source is in research/added_loads_sources.tsv. Missing BCs were scaled from the nearest-weight
  published load of the same cartridge (source=partial); price is estimated by brand tier.
- 10 and 16 Gauge (Oct 2026): 41 loads from the 2026 Federal, Winchester, Remington and Fiocchi
  catalogs (rows in research/added_loads_sources.tsv). BC is set by shot size like the other gauges;
  price is the same line's 12 ga price x1.25 (16 ga) or x1.6 (10 ga).
- Packaging variants are one load: bulk / pour pack / bucket / value or range pack / round-count
  boxes of the same product were merged (Oct 2026). Don't add them back as separate rows.
- Still Hornady-only (no other maker in the catalogs): .22 ARC, .25 Creedmoor, .30 T/C, .338 ARC,
  7mm STW. 8x57mm Mauser and .480 Ruger need PPU / S&B / Buffalo Bore data.

## Known to-dos
- Desktop layout fixed for HiDPI and checked under Xvfb; confirm on the real Fedora and
  Windows machines.
- The generic "typical" rows (7.62x54mmR, 5.45x39mm, 7.62x25mm Tokarev, .38 Super, .32 S&W Long)
  were taken out of Compare Loads (Oct 2026); they remain in Compare Cartridges and could be
  checked against real steel-case import data (Wolf, Tula, PPU) some day.
- Compare Loads (rifle/handgun) also lists every Compare Cartridges cartridge that has no factory
  loads (with_handload_only / withHandloadOnly), e.g. .32-40 Winchester, so it can hold handloads.
