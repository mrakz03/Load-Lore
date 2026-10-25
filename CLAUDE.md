# Load Lore (formerly Cartridge Calculator)

Working notes for contributors and AI coding assistants: the rules the code follows and why.

App name (Oct 2026): "In Like Flint - Load Lore" inside the app (APP_TITLE / web APP_TITLE, window
title, README heading); device menus show just "Load Lore" (issue #27: installer AppName and
shortcuts, .desktop Name, capacitor appName). File names were renamed too (Oct 2026): src/load_lore.py,
LoadLore.exe / LoadLore, install folders ...\Programs\Load Lore and ~/.local/share/load-lore (an
upgrade moves the old "Cartridge Calculator" / cartridge-calculator folder, user files included: the
.iss [Code] + external [Files], install.sh OLD_APPDIR). Kept on purpose:
Android appId com.cartridgecalc.app (changing it makes a new app: reinstall, handloads lost), the
Windows AppId, and the web's cartridge_calc_* localStorage keys (saved handloads/prices/settings).

Grades ammo S–F on velocity, energy, recoil, cost (plus Taylor KO and HITS;
default weights 3/3/1/3/3/3, Shotgun keeps Taylor KO and HITS at 0: no bullet diameter).
Desktop app: src/load_lore.py (Tkinter, stdlib only). Phone/web: web/template.html,
built by `python3 web/build_web.py` into web/www (Capacitor wraps it as an APK in CI).

## Rules
- Desktop and web scoring must stay in parity (same formulas, same data).
- Data lives in data/*.csv. After editing any CSV or the template, rebuild the web version.
- Two tools (Oct 2026; Compare Cartridges and "Add your own caliber" were removed): Load
  Dictionary (LoadsView / openLoads, the old Compare Loads, plus an S-F grades on/off switch kept
  in settings.json show_grades / localStorage) and Head to Head (HeadToHeadView / openH2H, 2-5
  loads side by side, from any category (Oct 2026): picks are (category, load) pairs, pick_key /
  pickKey include the category title, in App.h2h / H2H (one list), in memory only). Head to Head is
  one page (show_h2h / showH2H; no category picker, no sidebar sub-list, no weights panel): each
  load is graded with its own category's Load Dictionary weights (dict_weights / dictWeights),
  factors it lacks show "—", downrange steps come from the picked category with the largest step. Phones (<=600 px)
  get Head to Head as cards (one per load, one per factor with bars, downrange by distance chip),
  always naming loads, never numbering them. Head to Head load boxes are searches (issue #24:
  LoadSearch / searchBox, every typed word must be in the name); so are the cartridge boxes
  (Oct 2026): the dictionary's searches its category, Head to Head's searches every category
  (desktop rows "6.5 Creedmoor  ·  Centerfire Rifle", web list grouped under category headings).
  On touch screens (web, pointer: coarse) these boxes are read-only until the magnifier beside the
  arrow is tapped: a tap only opens the list to scroll (no keyboard, no text selection), and a
  pick closes the keyboard; a cartridge pick doesn't jump to the load box.
  Head to Head has no category box (Oct 2026): the cartridge box picks it; the desktop menu lists
  every category's cartridges under "──  Category  ──" headings (cart_menu). The dictionary's brand / load
  filter sits right above the list (issue #26). Beside it, for cartridges that have +P / +P+ loads, a check box each
  (pressure_of / pressureOf reads the load name; Train+Protect and +Peak aren't +P) hides those
  loads from the list without changing any grade; ticked by default, kept per category while the
  app is open (snapshot / shared), not in settings.json.
- Settings (Oct 2026, issue #17): theme, text size and the S-F grades switch live on one Settings
  page (show_settings / showSettings), reached from the bottom-left of the sidebar (a tab on phones),
  in two boxes, Display and About (rows split by thin lines, not one box each). About has a small
  GitHub logo that opens REPO_PAGE (GITHUB_MARK; web gets the URL as DATA.repo).
  The app name is drawn as a small "In Like Flint" over a larger "Load Lore" (issue #18).
- Ballistic table (dictionary, per load, collapsed by default): ballistic_table / ballisticTable,
  point-mass G1 path (trajectory / _fly, fly in web: drag along the path + gravity, RK2 0.5 m
  steps, bore tilted to cross the sight line at zero_yd) + 10 mph drift by Didion's lag rule,
  zero_yd / sight_in per category. Checked Oct 2026 against the Hornady 2026 ballistics pages:
  velocity and path match to ~0.1-0.3 in median error out to 500 yd (the old flat-fire t^2 drop
  read 10-15% too much drop at 400-500 yd). An estimate, not a full solver.
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
- Handload bullets go by diameter, not cartridge (one .257 bullet fits .250 Savage, .25-06, .257
  Roberts): the form lists only makers with a bullets.csv bullet of the cartridge's DIAMETERS
  size, then that maker's bullets; any other maker can be typed (desktop: editable boxes; web:
  "Other maker" opens a text box). Oct 2026: 61 bullets added for the diameters that had none
  (.257, .311/.312, .321, .323, .348, .365, .366, .410, .416, .475, .500, .510, .251), sources in
  research/added_bullets_sources.tsv (Nosler 2024 and Speer charts, Sierra pages, or the BC printed
  for the factory load with the same bullet). .221 (5.45x39mm) still has none.
- bullets.csv BCs are approximate; load figures are estimates; no safety validation of reloads.
- Recoil (recoil_ftlbs / recoil): standard free recoil, bullet + powder gas at GAS_FPS 4000, gas counted
  once (a 1.75x gas factor read 40-60% high; fixed Oct 2026 against Chuck Hawks' recoil table).
- Gun weight (Oct 2026): GUN_LB / typical_gun_lb (gun_lb, typicalGun in web) gives a typical gun per
  category + cartridge (.44 Magnum is in both rifle and handgun) where the category default is far off (.50 BMG 30 lb read 379 ft-lbs at 8 lb). The
  dictionary's gun field follows the cartridge unless the user typed their own (_gun_auto / L.gunAuto);
  Head to Head's gun weights are hidden by default ("Gun weight for each load" link: gun_open /
  gunOpen); opened, each load row gets its own box, blank = that cartridge's usual gun, and hiding
  them puts every load back in its usual gun (h2h_rows / h2hRows take a gun per load, in memory
  only, not shared with the dictionary). Limit GUN_LB_MAX 60 lb.
- .223 Remington, 5.56x45mm NATO, .308 Winchester and 7.62x51mm NATO are four separate cartridges
  (issue #28; they were two shared lists before). A NATO load says 5.56 / M193 / M855 or
  7.62x51 / M80 in its name; Hornady 5.56 NATO loads are the 20" barrel ones (checked against the
  2026 catalogs). Old saved data under the shared names goes through SPLIT_CARTRIDGES: handloads
  to the commercial cartridge, saved prices to both.
- Metric cartridges are named with "mm" (7.62x51mm NATO, 7.62x54mmR). When renaming a
  cartridge, add old -> new to RENAMED_CARTRIDGES so users' saved files keep matching.
- Colour themes live in THEMES (load_lore.py); build_web.py passes the same table to
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
- In-app updates (Windows/Linux, Settings > Updates, App.check_updates / start_update): asks the
  GitHub latest-release API, downloads the Setup.exe (run with /SILENT; the .iss [Run] entry with
  Check: WizardSilent reopens the app) or the Linux tar (install_linux_update swaps the files in
  place like install.sh), checked against SHA256SUMS.txt from the release job. "Check at start"
  (settings.json check_updates) is off by default. Release files carry the version
  (LoadLore-v1.7.4-dev-Setup.exe, -Windows.zip, -Linux.tar.gz, .apk; release_asset matches them).
  v1.7.3-dev and older only look for CartridgeCalculator-Setup.exe / -Linux.tar.gz, which releases
  no longer ship (the maintainer's call, Oct 24 2026): those copies are reinstalled by hand, and the
  installer / install.sh move the old folder and user files.
  SHA256SUMS.txt keeps its name.
  Tags are vX.Y.Z, optionally with a suffix for a test build (v1.7.2-dev sorts after 1.7.1, before
  1.7.2: version_tuple); a release marked "pre-release" on GitHub is skipped by the latest-release API.
git tag vX.Y.Z && git push origin vX.Y.Z  → GitHub Actions builds Windows (Setup.exe + zip), Linux
(tar with install.sh), Android (APK). Pull main first so the tag lands on the latest commit.
- APP_VERSION in load_lore.py stays "dev" in the repo; CI sets it from the tag.
- Versioning: small fix releases bump the last number (v1.5.1, v1.5.2); the maintainer saves
  the middle number (v1.6) for bigger releases.
- Installers upgrade in place and clear old shipped data (ammo_*, loads_*, bullets.csv) first.
- APK updates install over the old app only once the ANDROID_DEBUG_KEYSTORE secret is set
  (a debug.keystore made with keytool, base64 in the secret; the maintainer keeps the file); until then testers must uninstall the old APK first.

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
  Fiocchi, PMC and CCI catalogs (the maintainer's PDFs, not in the repo), plus a few Barnes, Nosler,
  Buffalo Bore, Sellier & Bellot and PPU loads from retailer listings. Every added row and its
  source is in research/added_loads_sources.tsv. Missing BCs were scaled from the nearest-weight
  published load of the same cartridge (source=partial); price was estimated by brand tier
  (re-set from retail Oct 24, see below).
- 10 and 16 Gauge (Oct 2026): 41 loads from the 2026 Federal, Winchester, Remington and Fiocchi
  catalogs (rows in research/added_loads_sources.tsv). BC is set by shot size like the other gauges;
  price is the same line's 12 ga price x1.25 (16 ga) or x1.6 (10 ga).
- Full catalog check (Oct 2026): every load in the 2026 Hornady (ballistics pages), Fiocchi, CCI/Blazer,
  PMC, ELEY, Remington, Winchester and Federal catalogs was matched against the data; the 47 missing
  ones were added (in research/added_loads_sources.tsv). Left out on purpose: cartridges the app doesn't
  have (Hornady Dangerous Game / Weatherby / Marlin Express etc., 30 Super Carry, 360 Buckhammer,
  7mm Backcountry, 338 Federal, Nitro Express, WSSMs, Fiocchi Heritage oddities), rimfire/handgun
  shotshells, less-lethal rounds, loads printed without ballistics, Remington bucket packs, and loads
  with no payload given (Hornady #4 Buck / Heavy Magnum Coyote / .410 Triple Defense, Winchester PDX1).
  Catalog misprints fixed from the energy column: Winchester S308M2 "652 gr" = 168 gr,
  Federal P40HSD1 "100 fps" = 1050 fps.
- Web-sourced loads (Oct 2026): 646 loads from maker websites, not the catalogs: SIG Sauer (sigsauer.com),
  Black Hills incl. Gold and HoneyBadger (black-hills.com), Norma (normausa.com; its spec tables are
  sometimes copied from another product, so the headline velocity is used), Nosler Trophy Grade
  and Defense (nosler.com), Federal Subsonic and Federal/Speer loads released after the 2026 catalog
  (federalpremium.com), Lapua (lapua.com), Sellier & Bellot (sellierbellot.us; m/s converted to fps),
  PPU (PPU's 2023 catalog PDF, its newest; 8x57 IS rows stand for 8x57mm Mauser, PPU's US-pressure
  "8mm Mauser" and "7mm Mauser" loads left out), Underwood (core handgun loads), Buffalo Bore
  (buffalobore.com), and IMI (retailer listings; IMI is mostly out of stock in the US). Missing BCs come
  from bullets.csv when the bullet is named, else are scaled from the nearest same-type load
  (source=partial); missing prices are the cartridge/purpose median x a brand factor (S&B and PPU
  further adjusted toward their real budget prices). Rows and URLs are in
  research/added_loads_sources.tsv. Black Hills 5.56mm loads carry "5.56mm" in the name because the
  same bullets are also sold as .223 Rem at different velocities. Barnes VOR-TX is not in: its site
  loads the specs by script.
- BC sweep (Oct 2026): each load's form factor (sectional density / BC) was compared with same-cartridge
  loads of similar weight. Catalog misprints fixed from the catalog's own downrange velocities (Fiocchi
  22-250 55 PSP 0.453 -> 0.239, Fiocchi 30-06 165 HPBT GK 0.224 -> 0.370, Remington .224 Valkyrie 90 OTM
  0.274 -> 0.572); bad scaled (partial) BCs on PPU HPBT and a few others set to the bullet's published BC.
  Hornady's Frontier line is in under "Hornady Frontier ..." (same ballistics as some Hornady loads).
- Packaging variants are one load: bulk / pour pack / bucket / value or range pack / round-count
  boxes of the same product were merged (Oct 2026). Don't add them back as separate rows.
- Data check (Oct 24 2026): bullets.csv Hornady ELD Match / ELD-X BCs set to hornady.com/bc (G1 at
  Mach 2.25; 6.5 147 gr is ELD Match, 6mm 103 gr is ELD-X, there is no .277 162 ELD-X), Nosler 30 cal
  150 BT 0.435. Slug BCs (were a flat 0.09 / 0.079) taken from the Remington and Winchester catalogs'
  own BC column, or fitted to Federal's downrange velocities. ELEY .22 LR prices from retail box
  prices (Lucky Gunner / KY Gun Co, Oct 2026).
- Retail prices (Oct 24 2026): every default_cost re-set from Lucky Gunner's category pages (PSA and
  MidwayUSA load prices by script, so they can't be read; Ammunition Depot has no round counts). A
  load matched to a listing (same brand, grain or payload, product line; smallest box listed) gets
  that per-round price (about 1,230 loads). The rest are scaled from the old brand-tier price by the
  matched loads of the same product line, else the same brand + old price in that cartridge, else a
  fitted cartridge x brand ratio (0.33-3x). ELEY kept. Each load's old/new price and method is in
  research/price_sources.tsv. Shotshells match by brand, line, length, payload / buck size.
- Still Hornady-only (no other maker in the catalogs): .22 ARC, .25 Creedmoor, .30 T/C, .338 ARC,
  7mm STW. .480 Ruger could use Buffalo Bore data.

## Known to-dos
- Desktop layout fixed for HiDPI and checked under Xvfb; confirm on the real Fedora and
  Windows machines.
- The generic "typical" rows (7.62x54mmR, 5.45x39mm, 7.62x25mm Tokarev, .38 Super, .32 S&W Long)
  were taken out of Compare Loads (Oct 2026); with Compare Cartridges gone they are only in
  ammo_*.csv. They could come back as branded loads from steel-case import data (Wolf, Tula, PPU).
- The Load Dictionary (rifle/handgun) also lists every ammo_*.csv cartridge that has no factory
  loads (with_handload_only / withHandloadOnly), e.g. .32-40 Winchester, so it can hold handloads.
