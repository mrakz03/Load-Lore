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
- Two tools plus Handloads (Oct 2026; Compare Cartridges and "Add your own caliber" were removed): Load
  Dictionary (LoadsView / openLoads, the old Compare Loads, plus an S-F grades on/off switch kept
  in settings.json show_grades / localStorage, off by default (Oct 25 2026); a saved choice is kept) and Head to Head (HeadToHeadView / openH2H, 2-5
  loads side by side, from any category (Oct 2026): picks are (category, load) pairs, pick_key /
  pickKey include the category title, in App.h2h / H2H (one list), in memory only). Head to Head is
  one page (show_h2h / showH2H; no category picker, no sidebar sub-list, no weights panel): each
  load is graded with its own category's Load Dictionary weights (dict_weights / dictWeights),
  factors it lacks show "—", downrange steps come from the picked category with the largest step. Its downrange table (Oct 2026) looks like the dictionary's ballistic table: compact (sized to its figures, not stretched to the window), each load's cartridge in small grey type, then its name on one line (only a very long name wraps), weight in small grey type under it, over its own right-aligned Velocity (fps) and Energy (ft-lbs) columns, a thin line between loads, each column highlighting its own leader at that distance. Phones (<=600 px)
  get Head to Head as cards (one per load, one per factor with bars, downrange by distance chip),
  always naming loads, never numbering them. "+ Add a load" adds an empty row (no copied cartridge) and
  opens nothing (Oct 27 2026, Zeke). Head to Head load boxes are searches (issue #24:
  LoadSearch / searchBox, every typed word must be in the name); so are the cartridge boxes
  (Oct 2026): the dictionary's searches its category, Head to Head's searches every category
  (desktop rows "6.5 Creedmoor  ·  Centerfire Rifle", web list grouped under category headings).
  None of these boxes take typing (so their text is never selected): on touch screens (web,
  pointer: coarse) a tap opens a bottom sheet (pickSheet: title, search bar that opens the
  keyboard only when tapped, the list; back button / backdrop / × close it); with a mouse /
  keyboard (desktop LoadSearch, web pickSheet with an anchor) a click, Down, Enter or a typed
  letter opens a search pop-up under the box (desktop: a Frame placed inside the box's own window,
  not a window of its own, so it can't float over other apps after Alt+Tab; cursor in its search field, Up/Down + Enter, Esc
  or a click outside closes, so do moving / resizing / minimising the window or switching apps:
  App._window_moved, LoadSearch._focus_left; rounded field with a magnifier, accent highlight, ✓ on the current
  pick, thin MUTED scrollbar: drawn on a Canvas on desktop, scrollbar-color on web). Empty boxes
  show the web's placeholder on desktop too (LoadSearch hint: Cartridge / Load / Pick a cartridge first). A cartridge pick doesn't jump to the load box.
  On touch screens a long pick wraps onto more lines instead of being cut off (Oct 28 2026, Zeke:
  .lsearch.wrap, a .lqv text layer over the input; box.sync re-reads the pick).
  Head to Head has no category box (Oct 2026): the cartridge box picks it; its pop-up lists
  every category's cartridges under category headings (LoadSearch head / searchBox head). The dictionary's brand / load
  filter sits right above the list (issue #26). Beside it, for cartridges that have +P / +P+ loads, a check box each
  (pressure_of / pressureOf reads the load name; Train+Protect and +Peak aren't +P) hides those
  loads from the list without changing any grade; ticked by default, kept per category while the
  app is open (snapshot / shared), not in settings.json.
- Handgun is a drop-down (Oct 28 2026, Zeke): Category.group="Handgun" on two categories, Handgun
  (menu "Pistol / Revolver", title kept so saved data matches) and Pistol Caliber Carbine; the picker
  card and the sidebar entry open / close them (menu_entries / menuEntries, open_groups / OPEN_GROUPS,
  GROUP_BLURBS; cat_name / catName for menus, page titles and cartridge-list headings). A cartridge in
  two categories reads "9mm Luger  ·  Carbine" (CAT_TAGS) in the handload form's box; lists under
  category headings show just the cartridge.
- Pistol Caliber Carbine: data/loads_pcc.csv, every row's source in research/pcc_sources.tsv.
  Maker-published carbine / lever-gun figures first (Buffalo Bore Marlin 1894 18-20", Hammerdown,
  Syntech PCC, Winchester rifle-barrel loads), then reviewer chronograph tests (source "tested"), then
  an estimate for every other handgun load of its cartridges (source "estimate", name ends " (est.)",
  SOURCE_NOTES + the category note say so): v16 = v x (16 / test barrel)^n, n fitted from loads
  printed at both lengths (auto 0.057, magnum revolver 0.221, standard revolver 0.132). Loads made
  for lever guns / carbines (Hammerdown, Syntech PCC, Gold Dot Carbine, LEVERevolution, American
  Lever Range) are PCC only, never in loads_handgun.csv. .357 / .44 Magnum left Centerfire Rifle
  (Zeke): MOVED_CATEGORIES moves saved handloads and prices. .22 LR / .22 WMR stay in Handgun.
- Settings (Oct 2026, issue #17): theme, text size and the S-F grades switch live on one Settings
  page (show_settings / showSettings), reached from the bottom-left of the sidebar (a tab on phones),
  in two boxes, Display and About (rows split by thin lines, not one box each). About has a small
  GitHub logo that opens REPO_PAGE (GITHUB_MARK; web gets the URL as DATA.repo).
  The app name is drawn as a small "In Like Flint" over a larger "Load Lore" (issue #18).
- Empty cartridge boxes (Oct 29 2026, Zeke): the dictionary's cartridge / gauge box and every Head to Head
  row start empty ("Choose a cartridge / gauge to see..."), never the cartridge with the most loads; a
  cartridge picked earlier while the app is open comes back (carry / shared), new Head to Head rows don't
  copy one.
- Default distance (Oct 28 2026, Zeke): 0 yd (the muzzle) in every category and in Head to Head
  (Category default_distance, H2H_DISTANCE), so the figures match the box; the field stays editable.
- Barrel length (Oct 29 2026, Zeke): the dictionary's settings card has a BARREL LENGTH (IN) On / Off
  switch (barrel_on / L.barrelOn, off by default; off = the listed figures exactly) with a length box
  while on, starting at Category.barrel_in (rifle / rimfire 24, handgun 4, PCC 16; shotgun 0 = no
  switch; under Distance on PC, phones swap Distance and gun weight so it sits under the gun weight: .dcell / .gcell / .bcell, Zeke Oct 29); kept per category while the app is open (snapshot / shared), not in settings.json. at_barrel /
  atBarrel copy each load (.base = the listed load, .at_in = the length) with v x (length / test
  barrel)^n, test barrel = barrel_in or the category's; barrel_exponent / barrelExp: handgun auto 0.057,
  standard revolver 0.132, magnum 0.221 (the PCC fits), .22s 0.07, rifles 0.10 + 0.25 x powder/bullet
  clamped 0.10-0.25. Everything (grades, recoil, ballistic table) follows the new speed; marked
  "(estimate)". Head to Head has "Barrel length for each load" like the gun weights (barrels in
  h2h_rows / h2hRows: the load's cartridge is graded at that length; blank / hidden = listed). The same load
  can be picked in two or more rows (Oct 29 2026, Zeke) to compare it at different barrel lengths / gun
  weights; such columns get an accent line naming what differs, "10.5 in barrel  ·  5 lb gun"
  (h2h_setups / h2hSetups). Head to Head's remembered gun / barrel boxes go by row position, not pick_key.
- Ballistic table (dictionary, per load, collapsed by default): ballistic_table / ballisticTable,
  point-mass G1 path (trajectory / _fly, fly in web: drag along the path + gravity, RK2 0.5 m
  steps, bore tilted to cross the sight line at zero_yd) + 10 mph drift by Didion's lag rule,
  zero_yd / sight_in per category. Checked Oct 2026 against the Hornady 2026 ballistics pages:
  velocity and path match to ~0.1-0.3 in median error out to 500 yd (the old flat-fire t^2 drop
  read 10-15% too much drop at 400-500 yd). An estimate, not a full solver.
- Back button (Oct 28 2026, Zeke): every web page change is a history entry (navigate -> navRecord:
  pushState with #loads/<category>, #h2h, #hand, #settings; Home has no hash), so the browser's back
  arrow and the phone's back button go to the previous in-app page; a reload or #address link opens
  that page (navFrom). Back with a dialog / pop-up open closes it and stays (popstate re-pushes).
  Android: the @capacitor/app backButton listener closes a dialog, else history.back() (state.depth),
  else steps category -> category list -> Home; only Home exits.
- data/loads_*.csv: every load name starts with its brand (Federal, Hornady, SIG Sauer...).
  data/ammo_*.csv: generic loads, no brand names; now only the cartridge list (handload-only
  cartridges, handload dialog).
  Generic rows never go in loads_*.csv, branded rows never in ammo_*.csv.
  ammo_*.csv names are bullet types only (Soft Point, Polymer Tip, Match BTHP, FMJ, JHP, Solid,
  Copper (lead-free)...), no product lines; it covers the common bases per cartridge, not every load.
- Grades are relative to the same cartridge and purpose (median/MAD, centre 70; shotshells
  within their load type): score_loads / scoreLoads. Head to Head shows each load's Load
  Dictionary grade (purpose All), never grades the picked loads against each other.
- Shot size sort (Oct 27 2026, Zeke): shotgun only, web "Sort: shot size" in the dictionary's sort
  menu, desktop a "Shot" column (click its heading). shot_size / shotSize read the load name's
  largest shot (slugs first, then 000-4 Buck, T/BBB/BB/B, #1-#9 as (17-n)/100 in), then most
  pellets, then heaviest payload.
- Grain weight sort (Oct 28 2026, Zeke): bullet categories (rifle, rimfire, handgun). Web sort menu
  "Sort: heaviest bullet" / "Sort: lightest bullet" (#ls grain / grainl); PC tables (desktop LoadsView, web
  >=900 px) have a Grains column whose heading sorts heaviest first, click again for lightest, so the
  Load cell there shows just the name (cards and labels keep "· 150 gr").
- Load labels read "Load  ·  150 gr" (make_label / makeLabel). Saved prices are keyed by label;
  keys from the old weight-first format are converted on read (_rename_price_key / readPrices).
- Handloads: my_handloads.csv (desktop) / localStorage (web). Never commit user files
  (my_calibers.csv, my_handloads.csv, settings.json).
- Handloads tab (Oct 2026: HandloadsView / show_hand, showHand in web): every handload of every
  bullet category; adding / editing / duplicating / deleting happen ONLY there (Zeke's call; the
  dictionary has a "Your handloads ›" link and "Edit in Handloads ›" on an open handload). The form
  (open_handload_dialog / handDialog) takes any category: the cartridge picks it (handload_cartridges
  / handCarts; a cartridge in two categories reads ".44 Magnum (Handgun)"). Cards show the
  dictionary grade via h2h_rows / h2hRows at the dictionary's distance.
  The safety line (tab, form, open handload) is HANDLOAD_NOTE, Zeke's LEGAL.md disclaimer verbatim
  (web gets it as DATA.hand_note), under a bold "DISCLAIMER" heading in the tab and form (disclaimer() /
  .dis). PC (desktop, web >=900 px) shows it right under the list; phones pin it to the bottom of
  the page, centred (.hpage flex column, .hnote margin-top:auto), or under the list once that is taller. Back up / Restore use the
  my_handloads.csv format (handload_csv_text / handCSV, merge_handload_rows / mergeHand: same id
  replaced, new added); the phone copies the CSV to the clipboard (no file save in Capacitor).
  On touch screens the form's pickers (cartridge, bullet maker, bullet, powder, purpose) open
  pickSheet too (sheetSelect puts a clear button over a <select>; powder has "Other powder (type
  it)"); pickSheet over a dialog hands the back button back to the dialog when it closes.
- Tab order (Oct 2026, Zeke): phones (NAVS) Home, Head to Head, Load Dictionary (the main tool, in the
  middle), Handloads, Settings; the PC sidebar (NAV_ORDER; web: CSS order at >=900 px, Oct 25) has
  the Load Dictionary above Head to Head. Home cards keep the Load Dictionary first (TOOLS).
- PC web load list (Oct 27 2026, Zeke): at >=900 px the dictionary's load list (#lres) is one table like
  the desktop app's (.lhead / .trow on a CSS subgrid, columns fit their figures, same columns as LoadsView;
  sortable headers set the #ls sort; clicking the sorted header again goes back to the default order, Grains goes heaviest -> lightest -> default, desktop _sort_by the same; Zeke, Oct 28 2026). Phones / <900 px keep the cards (.top); .lhead / .trow stay hidden there.
  At >=1500 px the dictionary page (.wrap.dict) fills the window: settings card, filter and sort in a
  left column, the table beside it; Head to Head (.wrap.h2hp) likewise puts the load picker in a left
  column (cartridge box over load box) beside the results; that column grows with the window (520 px at
  1500 px wide up to 720 px, so long load names fit; Zeke, Oct 28 2026), a load box's title shows the full name. An opened load on PC web shows a facts line
  and a tile per factor (.pdet, desktop panel style) instead of the phone's figure rows (.fr).
  Handloads (>=900 px): each cartridge group is a table too (Handload, Bullet, Powder, Velocity, Energy,
  Price, Grade; shares the #lres table CSS via :is(#lres,#hlist .lgrid)); >=1500 px it fills the window (.handp).
  The web handload form's cartridge box is a <select> (cartridges in an <optgroup> per category) with a
  .selcover button over it: with a mouse it opens the search pop-up (pickSheet with an anchor), on touch the
  bottom sheet, both with category headings (Zeke, Oct 28 2026; he tried the plain drop-down and preferred the pop-up).
- Before the public web launch (Oct 28 2026, Zeke): no "Development Build" text anywhere (version_text /
  VERSION_TEXT read "v1.10", or "dev" from source); Home ends with "Figures are estimates. Nothing you see
  here is reloading data. Disclaimer in Settings ›" (the Home line says "over 3,500 commercially available
  rounds": 3,685 loads in Oct 2026, update it if the count changes a lot) (desktop + web); the web page has a meta description and link-preview
  (og:) tags whose address is SITE in build_web.py (https://loadlore.net/, Zeke's custom domain for Pages), an apple-touch-icon and a
  manifest with display "browser" (a plain home-screen shortcut, no install prompt; Zeke wanted it
  unobtrusive). make_icons.py draws those icons into assets/web/; build_web.py copies them into www.
- PC Home, category list and Settings (Oct 25 2026, Zeke): top left, compact cards in one column (icon beside the text), zoomed
  with the window up to 1.15x (desktop App._menu_layout / _zoomed, re-laid out on resize; web
  fitMenu sets CSS zoom at >=900 px). Phones keep their centred layout.
- Handload bullets go by diameter, not cartridge (one .257 bullet fits .250 Savage, .25-06, .257
  Roberts): the form lists only makers with a bullets.csv bullet of the cartridge's DIAMETERS
  size, then that maker's bullets; any other maker can be typed (web:
  "Other maker" opens a text box; desktop: the form's pickers and the Settings theme box are
  LoadSearch pop-ups too, maker / bullet / powder with own=True, a last row 'Use "typed text"'). Oct 2026: 61 bullets added for the diameters that had none
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

- Desktop look follows the web (Oct 2026): rounded boxes are RoundBox (a canvas behind a .body
  Frame, smooth corners from corner_png, keep some padding or the body covers the corners), with
  App.card / App.button / App.chip (Pill) / App.field (rounded entry or drop-down, accent outline
  on focus) / Badge / close_button. Sidebar icons are the web's ICONS drawn by icon_png (stdlib PNG).

- App icon: scripts/make_icons.py (needs Pillow) draws assets/icon.png, icon.ico and the Android
  launcher icons in assets/android/res. CI bakes icon.ico into the .exe/installer, bundles
  icon.png for the window icon (icon_path), ships it in the Linux tar for the .desktop entry,
  and copies assets/android/res over the Capacitor project after `cap add android`.

## Release
- Build artifacts (the files on an Actions run page) are kept 7 days (retention-days); releases
  keep their own copies. Old private Load-Lore-old artifacts counted against the 500 MB free quota.
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
- Web version on GitHub Pages (Oct 27 2026, .github/workflows/pages.yml): a successful v* release build
  (workflow_run after "Build and release") or a manual run (Actions tab) builds main with build_web.py and
  deploys web/www (version = newest v* tag). A plain push to main does not deploy (Zeke, Oct 28 2026). Needs Settings > Pages > Source: GitHub
  Actions. A custom domain is set in Settings > Pages (no CNAME file with an Actions deploy).
- Beta web site (Oct 29 2026, Zeke): Cloudflare Pages (Zeke's Cloudflare account, no workflow in this repo)
  builds next on every push: build command `python3 web/build_web.py`, output web/www, env var
  LOADLORE_BETA=https://beta.loadlore.net/, served at https://beta.loadlore.net/. With LOADLORE_BETA set,
  build_web.py points og: tags there, titles the tab "In Like Flint - Load Lore (beta)", adds noindex (meta tag + a _headers file:
  X-Robots-Tag on every file) and makes the version
  "beta <commit>" (CF_PAGES_COMMIT_SHA). Its own address, so its localStorage is separate from the live site.
  (A first try pushed to a second repo, Load-Lore-beta; Zeke preferred no extra repo.)
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
- One shot size per load (Oct 27 2026): shotshell rows that listed every size a product is sold in
  ("3½" T/BBB/BB/2/3/4 Steel") were split into one row per size, same velocity, payload and price
  (the catalogs print one velocity per product), BC from the size and shot material (lead, steel,
  bismuth, TSS/tungsten; Winchester Last Call TSS and Longbeard Tungsten now use TSS BCs too).
  Shells holding two sizes stay one row: Federal Ultra Steel and Heavyweight TSS 7/9 read
  "BB x #2" / "#7 x #9", Winchester blends "BB+1.5". Where two speeds of the same line, size and
  payload met, both got "(1250 fps)". Old -> new names in research/split_shot_sizes.tsv.
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
- Oct 27 2026 gap fill: Buffalo Bore read cartridge by cartridge from buffalobore.com's category pages
  (index.php?l=product_list&c=N; c=146 handgun / c=147 rifle list them): 170+ loads, every cartridge the app has
  (the Sniper .223 loads are left out: their velocities are only in chart images). Federal's two .22 Creedmoor
  loads, Federal +Peak Barnes LRX, Winchester American Lever Range, Remington and Barnes subsonics. New cartridge
  4.6x30mm (Handgun category next to 5.7x28mm, 0.183 in, GUN_LB 4.5 lb for the MP7): Hornady BLACK V-MAX and
  Fiocchi FMJ / JSP / Hyperformance. bullets.csv has no .183 bullet. Rows and sources in added_loads_sources.tsv.
- Defensive rimfire (Oct 28 2026, Zeke): a defense load goes in each list it has published figures for, Handgun for a
  handgun-barrel velocity, Rimfire Rifle for a rifle one. Silvertip .22 LR / .22 WMR, Federal Punch, CCI Uppercut and
  Hornady Critical Defense .22 WMR print handgun figures only (Winchester marks Silvertip "handgun only"), so they are
  Handgun-only, purpose Defense. Winchester Defender .22 WMR has only the catalog's rifle figure (1910 fps), so it stays in
  Rimfire Rifle (purpose Hunting: a lone Defense load there would have nothing to be graded against).
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
