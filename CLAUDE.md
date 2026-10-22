# Cartridge Calculator

App name (Oct 2026): "In Like Flint - Load Lore" (APP_TITLE / web APP_TITLE, installer AppName,
.desktop Name, capacitor appName). Repo, file and package names (CartridgeCalculator.exe,
cartridge_calculator.py, appId com.cartridgecalc.app, Windows AppId and install folder) stay as
they were so updates keep installing over older versions.

Grades ammo S–F on velocity, energy, recoil, cost (plus Taylor KO and HITS;
default weights 3/3/1/3/3/3, Shotgun keeps Taylor KO and HITS at 0: no bullet diameter).
Desktop app: src/cartridge_calculator.py (Tkinter, stdlib only). Phone/web: web/template.html,
built by `python3 web/build_web.py` into web/www (Capacitor wraps it as an APK in CI).

## Rules
- Desktop and web scoring must stay in parity (same formulas, same data).
- Data lives in data/*.csv. After editing any CSV or the template, rebuild the web version.
- Two tools (Oct 2026; Compare Cartridges and "Add your own caliber" were removed): Load
  Dictionary (LoadsView / openLoads, the old Compare Loads, plus an S-F grades on/off switch kept
  in settings.json show_grades / localStorage) and Head to Head (HeadToHeadView / openH2H, 2-5
  loads of one category side by side, picks in App.h2h / H2H, in memory only). Phones (<=600 px)
  get Head to Head as cards (one per load, one per factor with bars, downrange by distance chip),
  always naming loads, never numbering them.
- Settings (Oct 2026, issue #17): theme, text size and the S-F grades switch live on one Settings
  page (show_settings / showSettings), reached from the bottom-left of the sidebar (a tab on phones).
  The app name is drawn as a small "In Like Flint" over a larger "Load Lore" (issue #18).
- Ballistic table (dictionary, per load, collapsed by default): ballistic_table / ballisticTable,
  flat-fire drop + 10 mph drift from flight_times / flightTimes (same G1 RK2 steps as velocity_at),
  zero_yd / sight_in per category. An estimate, not a solver.
- Android back button: @capacitor/app backButton listener in template.html closes a dialog, then
  steps category -> category list -> Home; only Home exits.
- data/loads_*.csv: every load name starts with its brand (Federal, Hornady, SIG Sauer...).
  data/ammo_*.csv: generic loads, no brand names; now only the cartridge list (handload-only
  cartridges, handload dialog).
  Generic rows never go in loads_*.csv, branded rows never in ammo_*.csv.
  ammo_*.csv names are bullet types only (Soft Point, Polymer Tip, Match BTHP, FMJ, JHP, Solid,
  Copper (lead-free)...), no product lines; it covers the common bases per cartridge, not every load.
- Grades are relative to the same cartridge and purpose (median/MAD, centre 70; shotshells
  within their load type): score_loads / scoreLoads. Head to Head shows each load's Load
  Dictionary grade (purpose All), never grades the picked loads against each other.
- Load labels read "Load  ·  150 gr" (make_label / makeLabel). Saved prices are keyed by label;
  keys from the old weight-first format are converted on read (_rename_price_key / readPrices).
- Handloads: my_handloads.csv (desktop) / localStorage (web). Never commit user files
  (my_calibers.csv, my_handloads.csv, settings.json).
- bullets.csv BCs are approximate; load figures are estimates; no safety validation of reloads.
- .223 Remington / 5.56x45mm NATO and .308 Winchester / 7.62x51mm NATO are one list each, but a
  load's details and Head to Head name the one cartridge it is made for (SHARED_CHAMBERS /
  chambered, same rules on web): a NATO load must say 5.56 / M193 / M855 or 7.62x51 / M80 in its
  name; Hornady 5.56 NATO loads are the 20" barrel ones (checked against the 2026 catalogs).
- Metric cartridges are named with "mm" (7.62x51mm NATO, 7.62x54mmR). When renaming a
  cartridge, add old -> new to RENAMED_CARTRIDGES so users' saved files keep matching.
- Colour themes live in THEMES (cartridge_calculator.py); build_web.py passes the same table to
  the web version. Classic is the default and the original look. Use the palette globals
  (BG, SURFACE, TEXT, ACCENT, ON_ACCENT, DANGER, HAND_FG...) / CSS variables, never hard-coded colours.
- Desktop UI sizes come from measured text (App.fit_columns, _sidebar_width), not fixed pixel
  counts: fonts are in points and grow with screen DPI, so fixed widths cut text off on HiDPI.
  The Load column fits the longest full name, re-measured per cartridge; grow_to_fit widens
  the window for it and gives the room back later, never below the width the user chose.
  LoadsView.fit_table_height sets the table's row count from the window height so the
  selected load's (larger) panel fits without scrolling: at most OPEN_ROWS while a load is open,
  the full height when closed (min 6 rows, then the page scrolls).
  App.px() scales by text size AND screen DPI (self.dpi, 96 dpi = 1.0). On Windows,
  sharp_on_windows() declares DPI awareness before Tk starts, otherwise Windows stretches the
  window and it looks blurry (issue #5).

- App icon: scripts/make_icons.py (needs Pillow) draws assets/icon.png, icon.ico and the Android
  launcher icons in assets/android/res. CI bakes icon.ico into the .exe/installer, bundles
  icon.png for the window icon (icon_path), ships it in the Linux tar for the .desktop entry,
  and copies assets/android/res over the Capacitor project after `cap add android`.

## Release
git tag vX.Y.Z && git push origin vX.Y.Z  → GitHub Actions builds Windows (Setup.exe + zip), Linux
(tar with install.sh), Android (APK). Pull main first so the tag lands on the latest commit.
- APP_VERSION in cartridge_calculator.py stays "dev" in the repo; CI sets it from the tag.
- Versioning: small fix releases bump the last number (v1.5.1, v1.5.2); the user saves the
  middle number (v1.6) for bigger releases.
- Installers upgrade in place and clear old shipped data (ammo_*, loads_*, bullets.csv) first.
- APK updates install over the old app only once the ANDROID_DEBUG_KEYSTORE secret is set
  (see README); until then testers must uninstall the old APK first.

## Testing
- Desktop: python3.12 has Tk here (the default python3 doesn't); drive App headlessly under
  xvfb-run, patching messagebox so popups don't block. Try `tk scaling 2.0` for HiDPI.
- Web: Playwright from /opt/node-tools/node_modules against web/www/index.html.
- Parity: compare score_loads/h2h_rows/h2h_downrange with the web's scoreLoads/h2hRows/h2hDownrange.

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
  were taken out of Compare Loads (Oct 2026); with Compare Cartridges gone they are only in
  ammo_*.csv. They could come back as branded loads from steel-case import data (Wolf, Tula, PPU).
- The Load Dictionary (rifle/handgun) also lists every ammo_*.csv cartridge that has no factory
  loads (with_handload_only / withHandloadOnly), e.g. .32-40 Winchester, so it can hold handloads.
