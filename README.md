# In Like Flint - Load Lore

<img src="assets/icon.png" alt="App icon: a rifle cartridge standing on a book" width="96" align="right">

A field guide to factory ammunition. Look up every brand's load for a cartridge, see how it grades from S to F against the others, read its ballistic table, and put up to five loads head to head. Reloaders can add their own handloads and see how they stack up against factory ammo.

**Try it in your browser at [loadlore.net](https://loadlore.net)**, no install needed (it works on phones too). It also runs as a desktop app on Windows and Linux and as a phone app on Android.


> **Still in development.** Load Lore is a work in progress. Most of it works well, but some parts aren't fully polished yet, and you may run into rough edges, layout quirks or a load whose figures need fixing. If something looks wrong, please [open an issue](https://github.com/mrakz03/Load-Lore/issues).

## What's inside

About 3,650 factory loads from 20 makers across four categories, plus a Pistol Caliber Carbine section under Handgun:

| Category | Cartridges | Loads |
|---|---|---|
| Centerfire Rifle | 74 | 1,504 |
| Handgun | 30 | 909 |
| ↳ Pistol Caliber Carbine | 14 | 732 |
| Rimfire Rifle | 7 | 128 |
| Shotgun (10, 12, 16, 20, 28 gauge and .410 bore) | 6 | 1,124 |

The loads come from the 2026 catalogs of Hornady, Federal, Winchester, Remington, Fiocchi, PMC, CCI/Blazer and ELEY, and from the makers' own websites for SIG Sauer, Black Hills, Norma, Nosler, Lapua, Sellier & Bellot, PPU, Underwood, Buffalo Bore, Speer and newer Federal loads (plus a few Barnes, IMI, Winchester and Federal loads from retailer listings). Weight and velocity are the maker's published figures; prices and powder charges are estimates. Where each added load came from is listed in `research/added_loads_sources.tsv`.

The **Pistol Caliber Carbine** section (picked from the Handgun menu) holds handgun cartridges fired from carbine and lever-gun barrels, such as 9mm Luger, .357 Magnum, .44 Magnum and 10mm Auto. Its loads use the maker's published carbine velocity where there is one; most makers only print a handgun figure, so those loads are marked **(est.)** and their velocity is worked out for a 16 in barrel.

## Using the app

### Load Dictionary
Pick a category (Handgun opens a small menu: Pistol / Revolver or Pistol Caliber Carbine), then a cartridge, and every load for it is listed and ranked.

- **Grades.** Each load gets a letter from S to F on velocity, energy, recoil, cost, Taylor KO and HITS, plus an overall grade. Grades compare loads of the *same* cartridge with each other: the average load scores about 70, a B. The **S–F grades: On / Off** switch on the Settings page hides the grades and scores if you just want the numbers; the app remembers your choice. (This is added for you Fudds that will complain that your favorite load somehow got ranked as an F).
- **Filter and sort.** Narrow the list by purpose (Hunting, Varmint, Target, Match, Defense, Subsonic; shotguns by load type) or type a brand or load name in the filter box right above the list. Click a column heading (desktop app and PC browsers) or use the sort menu next to the filter box (phone). Besides grade, price, velocity, energy and recoil you can sort by bullet weight (heaviest or lightest first), and shotgun loads by shot size (slugs, then buckshot, then the largest birdshot first).
- **Distance and gun weight.** Velocity, energy, Taylor KO and HITS are worked out at the distance you enter, which starts at 0 yd (the muzzle) so the figures match the box; recoil uses the gun weight you enter. The weight starts at a typical gun for the cartridge: 8 lb for most rifles, but 30 lb for .50 BMG, 15 lb for .338 Lapua, around 10 lb for the big dangerous-game rounds and heavier revolvers for the magnum handgun rounds. If you type your own weight it stays put when you switch cartridges. In Head to Head, leave the weight blank to put each load in its own cartridge's typical gun.
- **Selected load.** Click a load to open its panel: every figure with its grade, the test barrel length, where the data came from, and:
  - **Ballistic table** (▸ to open): velocity, energy, path (inches above or below the line of sight) and drift in a 10 mph crosswind, from the muzzle out to 500 yd for centerfire rifles (shorter steps for handgun, rimfire and shotgun). Rifles assume a 100 yd zero with the sight 1.5 in above the bore; handguns 25 yd and 0.6 in; pistol caliber carbines 50 yd and 2 in; rimfire 50 yd; slugs 50 yd. These are estimates from the ballistic coefficient in standard sea-level air, not a full ballistic solver.
  - **Your price.** Prices are catalog-based estimates; type what you actually pay per round and the cost grade updates.
  - **+ Head to Head** adds the load to the Head to Head tab.
- **Scoring weights.** Decide how much each factor counts (0 ignores it). The defaults are 3 for everything except recoil (1); rimfire weighs cost double, and shotguns skip Taylor KO and HITS.

### Head to Head
Pick 2 to 5 loads from any cartridges, for example a .308 Winchester load against a 6.5 Creedmoor load, or add them from the Load Dictionary. Head to Head is one page for every category, so loads can come from different categories too (a 12 gauge slug against a .30-30 Winchester): the cartridge box searches every category and lists its matches under category headings. A factor that doesn't apply to a load (shotguns have no Taylor KO or HITS) shows a dash, and every load keeps the grade its own Load Dictionary gives it, with that category's scoring weights. To find a load quickly, type in its load box: every word you type has to appear in the name (for example `hornady 55` or `federal match`), then pick from the matches with a click or tap, or the arrow keys and Enter. You see:

- every figure side by side, with the best one highlighted and how far behind the others are, in %;
- how many factors each load wins;
- each load's grade and rank from the Load Dictionary (against its own cartridge, so the two tabs always agree);
- a downrange table of velocity and energy.

On a phone this is laid out as cards: one per load, then one per factor with a bar for each load, then downrange at the distance you pick.

### Handloads
The **Handloads** tab keeps all your own loads, from every category, in one place. **+ New handload** opens a form for your own load: cartridge (any rifle, handgun or rimfire cartridge), bullet (pick a maker and bullet from the built-in library, which goes by bullet diameter, or type your own), powder and charge, velocity, barrel length, purpose and cost per round (a total, or bullet + powder + primer + brass with the number of times you reuse the brass). Each handload shows its grade against the factory loads of its cartridge and can be edited, duplicated, deleted, opened in the Load Dictionary (where it's listed with the factory loads, marked in a different color) or put head to head.

**Back up** saves your handloads as a CSV file (on the phone: copies it, to paste into a note or email), and **Restore** reads one back, so you can move handloads between the computer and the phone.

Handload figures are only as good as your data. The app does not check pressure or safety: always follow a published load manual.

### Settings
Theme (several color schemes; Classic is the original dark look), text size and the S–F grades switch are on the Settings page: at the bottom of the sidebar on desktop, and the Settings tab on the phone. On Android, the back button steps back through the menus; on the Home screen it closes the app.

## How the grades work
For each factor, a load is scored on a curve against the typical (median) load of the same cartridge, so going further past typical earns less and less. The factor scores are spread out so that the typical load sits at 70 and one "typical spread" (median absolute deviation) moves it about 10 points, then combined using the scoring weights. Letter grades: S 85+, A 77+, B 66+, C 55+, D 45+, F below. Shotshells are only compared with the same load type (target with target, buckshot with buckshot, slugs with slugs).

- **Taylor KO**: bullet weight (gr) × velocity (fps) × diameter (in) ÷ 7000.
- **HITS** (Hornady Index of Terminal Standards): (weight² ÷ 7000) × (velocity ÷ diameter²) ÷ 100, shown with Hornady's game-size class.
- **Velocity downrange**: integrated from the G1 drag model using each load's G1 ballistic coefficient.
- **Recoil**: free recoil energy for a gun of the weight you enter (up to 60 lb): the gun takes the momentum of the bullet plus the powder gas (leaving at about 4000 fps). Powder charges are estimates, so figures are within about 10% of published recoil tables such as Chuck Hawks'.

## Download and install
The quickest way in is the web version at **[loadlore.net](https://loadlore.net)**: it runs in any browser on a computer or phone and is always up to date. Your handloads, prices and settings stay in that browser (use **Back up** in Handloads to move them). On a phone you can add it to your home screen from the browser's menu.

The apps are on the repository's **Releases** page.

- **Windows**: run `LoadLore-v<version>-Setup.exe` (for example `LoadLore-v1.10-Setup.exe`). It installs for the current user (no admin password), adds Start menu and desktop shortcuts, and can be removed from Settings > Apps. A newer installer upgrades in place and keeps your handloads and settings. The installer isn't code-signed, so SmartScreen may say "Windows protected your PC": click More info, then Run anyway. A portable .zip is also available.
- **Linux**: unpack and run the installer, which adds the app to your launcher. Run it again with a newer release to update (your own files are kept), or with `--uninstall` to remove it.
  ```
  tar xzf LoadLore-v*-Linux.tar.gz
  bash LoadLore/install.sh
  ```
- **Android**: install `LoadLore-v<version>.apk` (allow installs from your browser or file manager when asked).

**Updating (Windows and Linux):** open Settings and press **Check for updates**. When a newer release is out, **Update to vX** downloads it, checks it against the release's `SHA256SUMS.txt`, installs it over the old version and reopens the app; your handloads, prices and settings are kept. Turn on **Check at start** to be asked whenever a new version comes out. The app only talks to GitHub when you press the button or turn that on. The portable Windows .zip can't update itself, so its button opens the Releases page instead.

In the Start menu, app launcher and phone app drawer the app is called **Load Lore**. Download files carry the version in their name. Copies of v1.7.3-dev and older can't update themselves to the renamed version: download and run the new installer (or install.sh) once. It moves the app from the old Cartridge Calculator folder to a Load Lore folder, handloads and settings included.

## For developers

### Repository layout
```
src/load_lore.py              desktop app (single file, Python standard library + Tkinter only)
web/template.html             phone/web app (single page, no framework)
web/build_web.py              embeds the CSV data into web/www/index.html
data/loads_*.csv              factory loads, one file per category
data/ammo_*.csv               cartridge list (cartridges with no factory loads can still hold handloads)
data/bullets.csv              bullet library for the handload form (weight, diameter, approximate G1 BC)
assets/                       app icons (drawn by scripts/make_icons.py, needs Pillow)
scripts/build_linux.sh        build from source and install on Fedora / Linux
scripts/install_linux.sh      installer shipped in the Linux release (as install.sh)
scripts/build_windows.bat     build the Windows .exe locally
scripts/windows_installer.iss Inno Setup script for the Windows installer (built in CI)
.github/workflows/release.yml builds Windows, Linux and Android
.github/workflows/pages.yml   publishes the web version to loadlore.net (GitHub Pages)
package.json, capacitor.config.json   Android wrapper (Capacitor)
research/                     where each added load came from
```

### Running from source
```
python3 src/load_lore.py                   # desktop app (needs Tk: python3-tkinter)
python3 web/build_web.py                   # then open web/www/index.html in a browser
```
The web version at loadlore.net is built from `main` by `.github/workflows/pages.yml` after each release, or when run by hand from the Actions tab (Web version on GitHub Pages > Run workflow). Pushing to `main` alone doesn't change the site.
Handloads (`my_handloads.csv`) and settings (`settings.json`) are saved next to the data files and are git-ignored; the phone/web version keeps them in the browser. The desktop and web versions use the same formulas and data and must stay in step: after editing any CSV or `web/template.html`, run `python3 web/build_web.py`.

### Data files
- `loads_*.csv` columns: cartridge, load, bullet_gr, muzzle_fps, bc_g1, powder_gr, default_cost, default, source, group, barrel_in, purpose (and optionally diameter_in). Every load name starts with its brand. `barrel_in` is the test barrel length; `purpose` is Hunting / Varmint / Target / Match / Defense / Subsonic (shotguns use `group`, their load type).
- `ammo_*.csv` holds generic loads with no brand names; it provides the cartridge list.
- 5.56x45mm NATO and 7.62x51mm NATO are their own cartridges, separate from .223 Remington and .308 Winchester. A NATO load says so in its name (5.56, M193, M855, 7.62x51, M80); Hornady's 5.56 NATO loads are the ones tested in a 20" barrel. Handloads and prices saved when they shared one list are matched up through `SPLIT_CARTRIDGES`.
- Saved handloads and prices that use older names are matched up automatically through `RENAMED_CARTRIDGES` in `src/load_lore.py`.
- Bullet diameters for Taylor KO and HITS come from the `DIAMETERS` table in the same file.
- `bullets.csv` BCs are approximate published G1 figures.

## Contributing
Bug reports, load corrections and ideas are welcome as GitHub issues. For a data fix, name the load and give the source (maker's catalog page or website) for the numbers. Pull requests should keep the desktop and phone versions in step (same formulas, same data) and rebuild the web version after changing a CSV or `web/template.html`. `CLAUDE.md` holds the project's working notes and rules in more detail. I have shit to do IRL so I might not be the fastest at looking at your forks/PRs, but please feel free to improve this program and send over any suggestions!

## License

Free software under the [MIT License](LICENSE): use, change and share it, with no warranty. Brand names identify products only; no maker sponsors or endorses this app.

**Read [LEGAL.md](LEGAL.md)** before relying on the app: figures are estimates, the powder charges are not reloading data, and the ballistic table is not for real shooting decisions. It also has the trademark notes, where the load data comes from, and the licenses of the bundled software.
