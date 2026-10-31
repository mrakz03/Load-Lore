# In Like Flint - Load Lore

<img src="assets/icon.png" alt="App icon: a rifle cartridge standing on a book" width="96" align="right">

A field guide to factory ammunition. Look up major brand's loads for a cartridge, get specs for each load, check their ballistic tables, and put up to five loads head to head. Reloaders can add their own handloads and see how they stack up.

**Try it in your browser at [loadlore.net](https://loadlore.net)**, no install needed (it works on phones too). It also runs as a desktop app on Windows and Linux and as an Android app.

> **Still in development.** Most of it works well, but you may run into rough edges, a load whose figures need fixing, or a missing factory load. If something looks wrong or you have any suggestions, please [open an issue](https://github.com/mrakz03/Load-Lore/issues).

<br>

## Read [LEGAL.md](LEGAL.md)

Please read [LEGAL.md](LEGAL.md) before using the app: figures are estimates, the powder charges are not reloading data, and the ballistic tables are not for real shooting decisions. Brand names identify products only; no maker sponsors or endorses this software. It also has the trademark notes, where the load data comes from, and the licenses of the bundled software.

<br>

## What's inside

About 3,650 factory loads from 20 makers, in four categories (plus a Pistol Caliber Carbine section under Handgun):

| Category | Cartridges | Loads |
|---|---|---|
| Centerfire Rifle | 74 | 1,506 |
| Handgun | 30 | 909 |
| ↳ Pistol Caliber Carbine | 14 | 732 |
| Rimfire Rifle | 7 | 128 |
| Shotgun (10, 12, 16, 20, 28 gauge and .410 bore) | 6 | 1,124 |

Velocity and bullet weight are the makers' own published figures, from the 2026 catalogs of Hornady, Federal, Winchester, Remington, Fiocchi, PMC, CCI/Blazer and ELEY and from the websites of SIG Sauer, Black Hills, Norma, Nosler, Lapua, Sellier & Bellot, PPU, Underwood, Buffalo Bore and Speer (plus a few loads from retailer listings). Prices and powder charges are estimates. The source of every added load is in `research/added_loads_sources.tsv`.

**Pistol Caliber Carbine** covers handgun cartridges fired from carbines and lever guns (9mm, .357 Magnum, .44 Magnum, 10mm and more). Where a maker publishes a carbine velocity it is used; the rest are marked **(est.)** and worked out for a 16 in barrel from the maker's handgun figure.

<br>

## Features

### Load Dictionary
Look up every load for a cartridge, graded and ranked.

- **Pick a cartridge.** Choose a category (Handgun opens Pistol / Revolver, or Pistol Caliber Carbine), then search for a cartridge.
- **Filter and sort.** Filter by purpose (Hunting, Defense, Match...) or by typing a brand or load name. Hide +P / +P+ loads with a check box. Sort by grade, price, velocity, energy, recoil, bullet weight or, for shotguns, shot size.
- **Grades.** This setting is off by default, to not distract you from the data shown. If enabled, each load gets a letter from S to F for velocity, energy, recoil, cost, Taylor KO and HITS, plus an overall grade. Loads are graded against others of the *same* cartridge, so an average load is a B.
  - **Scoring weights.** If grades are enabled, these options will appear. Choose how much each factor counts toward the overall grade (0 ignores it).
- **Distance.** Figures are shown at the distance you enter, starting at the muzzle (0 yd).
- **Firearm setup.** Out of the box, the figures are the makers' published data. Enter your own gun weight, barrel length and twist rate to get estimates for your firearm: velocity is scaled to your barrel, recoil to your gun's weight, and the twist rate warns (⚠) when a bullet won't spin fast enough to stay stable. **Reset to maker's figures** goes back to the published data.
- **Open a load** to see every spec figure for the selected load, and:
  - **about your figures**: click to see data for where given figures came from;
  - **ballistic table**: velocity, energy, bullet drop and wind drift out to 500 yd (rifles) or a shorter range (handguns, rimfire, slugs);
  - **your price**: type what you actually pay per round and the cost grade updates;
  - **+ Head to Head** to add the load to your head-head comparison.

### Head to Head
Compare 2 to 5 loads side by side, from any cartridge or category (a .308 against a 6.5 Creedmoor, or a 12 gauge slug against a .30-30).

- Search for a cartridge, then a load: every word you type has to be in the name (for example `hornady 55`).
- See every figure side by side with the leader highlighted, how many factors each load wins, each load's grade from the Load Dictionary, and a downrange table.
- **Firearm setup for each load** gives each load its own gun weight, barrel and twist. Pick the same load twice to compare it from, say, a 10.5 in and a 16 in barrel.
- On phones the comparison is shown as easy-to-scroll cards.

### Handloads
Keep your own loads and see how they grade against factory ammo of the same cartridge.

- **+ New handload**: pick the cartridge, bullet (from the built-in library or type your own), powder and charge, velocity, barrel length, purpose and cost (a total, or worked out from components and brass reuse).
- Edit, duplicate or delete handloads, see them listed with the factory loads in the Load Dictionary, or put them head to head.
- **Back up / Restore** saves your handloads as a CSV file, so you can move them between computer and phone.

The app does not check pressure or safety. Always follow a published load manual.

### Settings
- Theme, text size and the grades on/off switch. On Windows and Linux, Settings also has **Check for updates**.

<br>

## How the numbers work
Each factor is scored against the typical (median) load of the same cartridge: the typical load scores 70, and going far past typical earns less and less. The factor scores are combined using the scoring weights (default 3 for everything, 1 for recoil; rimfire counts cost double, shotguns skip Taylor KO and HITS). Grades: S 85+, A 77+, B 66+, C 55+, D 45+, F below. Shotshells are only compared within their load type (buckshot with buckshot, slugs with slugs). 

- **Taylor KO**: bullet weight (gr) × velocity (fps) × diameter (in) ÷ 7000.
- **HITS** (Hornady Index of Terminal Standards): (weight² ÷ 7000) × (velocity ÷ diameter²) ÷ 100.
- **Recoil**: free recoil energy for your gun weight, counting the bullet and the powder gas. Within about 10% of published recoil tables.
- **Downrange and ballistic table**: G1 drag model from each load's ballistic coefficient, in standard sea-level air. An estimate, not a full ballistic solver.
- **Barrel length**: velocity × (your barrel ÷ test barrel)^n, with n fitted from loads published at two barrel lengths. Checked against .300 Blackout chronograph tests: within about 10 fps.
- **Twist rate**: Miller's stability rule with an estimated bullet length. Twist never changes velocity or grades; a barely stable bullet loses a little ballistic coefficient.

<br> 

## Download and install
The easiest way is the web version at **[loadlore.net](https://loadlore.net)**: it runs in any browser, on a computer or phone, and is always up to date. Your handloads and settings stay in that browser (use **Back up** in Handloads to move them).

The apps are on the [Releases](https://github.com/mrakz03/Load-Lore/releases) page.

- **Windows**: run `LoadLore-v<version>-Setup.exe`. No admin password needed, and a newer installer upgrades in place, keeping your handloads and settings. The installer isn't code-signed, so if Windows says "Windows protected your PC", click More info, then Run anyway. A portable .zip is also available.
- **Linux**: unpack and run the installer, which adds the app to your launcher. Run it again with a newer release to update, or with `--uninstall` to remove it.
  ```
  tar xzf LoadLore-v*-Linux.tar.gz
  bash LoadLore/install.sh
  ```
- **Android**: install `LoadLore-v<version>.apk` (allow installs from your browser or file manager when asked).

**Updating (Windows and Linux):** in Settings press **Check for updates**, then **Update**. The download is checked against the release's `SHA256SUMS.txt` and installed over the old version; your data is kept. **Check at start** asks you whenever a new version is out. The app only contacts GitHub when you ask it to.

Upgrading from v1.7.3-dev or older (when the app was called Cartridge Calculator)? Run the new installer or install.sh once by hand. It moves your handloads and settings over.

<br>

## For developers

### Repository layout
```
src/load_lore.py              desktop app (single file, Python standard library + Tkinter only)
web/template.html             phone/web app (single page, no framework)
web/build_web.py              embeds the CSV data into web/www/index.html
data/loads_*.csv              factory loads, one file per category (loads_pcc.csv: Pistol Caliber Carbine)
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
research/                     where each added load came from (pcc_sources.tsv for the carbine loads)
```

### Running from source
```
python3 src/load_lore.py                   # desktop app (needs Tk: python3-tkinter)
python3 web/build_web.py                   # then open web/www/index.html in a browser
```
The desktop and web versions share the same formulas and data and must stay in step: after editing any CSV or `web/template.html`, run `python3 web/build_web.py`. The site at loadlore.net is rebuilt from `main` after each release (or by running the Pages workflow by hand); a plain push doesn't change it. Your own handloads (`my_handloads.csv`) and settings (`settings.json`) are git-ignored.

### Data files
- `loads_*.csv` columns: cartridge, load, bullet_gr, muzzle_fps, bc_g1, powder_gr, default_cost, default, source, group, barrel_in (test barrel), purpose, and optionally diameter_in. Every load name starts with its brand; shotguns use `group` for the load type.
- `ammo_*.csv` holds generic, unbranded loads and provides the cartridge list.
- .223 Remington / 5.56x45mm NATO and .308 Winchester / 7.62x51mm NATO are separate cartridges; a NATO load says so in its name (5.56, M193, M855, 7.62x51, M80).
- When renaming or splitting a cartridge, add it to `RENAMED_CARTRIDGES` or `SPLIT_CARTRIDGES` in `src/load_lore.py` so saved handloads and prices still match. Bullet diameters are in the `DIAMETERS` table there.

<br>

## Contributing
Bug reports, load corrections and ideas are welcome as [GitHub issues](https://github.com/mrakz03/Load-Lore/issues). For a data fix, name the load and link the maker's catalog page or website. Pull requests should keep the desktop and web versions in step. `CLAUDE.md` has the project's detailed working notes. I have shit to do IRL so I might not be the fastest at looking at your forks/PRs, but please feel free to improve this program and send over any suggestions!

<br>

## License

Free software under the [MIT License](LICENSE): use, change and share it, with no warranty. 
