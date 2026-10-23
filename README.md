# In Like Flint - Load Lore

<img src="assets/icon.png" alt="App icon: a rifle cartridge standing on a book" width="96" align="right">

A field guide to factory ammunition. Look up every brand's load for a cartridge, see how it grades from S to F against the others, read its ballistic table, and put up to five loads head to head. Reloaders can add their own handloads and see how they stack up against factory ammo.

It runs as a desktop app on Windows and Linux and as a phone app on Android (the phone version also works in any web browser).

*Formerly Cartridge Value Calculator.*

## What's inside

About 2,460 factory loads across four categories:

| Category | Cartridges | Loads |
|---|---|---|
| Centerfire Rifle | 75 | 1,001 |
| Handgun | 29 | 567 |
| Rimfire Rifle | 7 | 129 |
| Shotgun (10, 12, 16, 20, 28 gauge and .410 bore) | 6 | 763 |

The loads come from the 2026 catalogs of Hornady, Federal, Winchester, Remington, Fiocchi, PMC, CCI and ELEY, plus Speer Gold Dot / Lawman and a few Barnes, Nosler, Buffalo Bore, Sellier & Bellot and PPU loads. Weight and velocity are the maker's published figures; prices and powder charges are estimates.

## Using the app

### Load Dictionary
Pick a category, then a cartridge, and every load for it is listed and ranked.

- **Grades.** Each load gets a letter from S to F on velocity, energy, recoil, cost, Taylor KO and HITS, plus an overall grade. Grades compare loads of the *same* cartridge with each other: the average load scores about 70, a B. The **S–F grades: On / Off** switch hides the grades and scores if you just want the numbers; the app remembers your choice.
- **Filter and sort.** Narrow the list by purpose (Hunting, Varmint, Target, Match, Defense, Subsonic; shotguns by load type) or type a brand or load name. Click a column heading (desktop) or use the sort menu (phone).
- **Distance and gun weight.** Velocity, energy, Taylor KO and HITS are worked out at the distance you enter; recoil uses the gun weight you enter.
- **Selected load.** Click a load to open its panel: every figure with its grade, the test barrel length, where the data came from, and:
  - **Ballistic table** (▸ to open): velocity, energy, path (inches above or below the line of sight) and drift in a 10 mph crosswind, from the muzzle out to 500 yd for centerfire rifles (shorter steps for handgun, rimfire and shotgun). Rifles assume a 100 yd zero with the sight 1.5 in above the bore; handguns 25 yd and 0.6 in; rimfire 50 yd; slugs 50 yd. These are estimates from the ballistic coefficient in standard sea-level air, not a full ballistic solver.
  - **Your price.** Prices are catalog-based estimates; type what you actually pay per round and the cost grade updates.
  - **+ Head to Head** adds the load to the Head to Head tab.
- **Scoring weights.** Decide how much each factor counts (0 ignores it). The defaults are 3 for everything except recoil (1); rimfire weighs cost double, and shotguns skip Taylor KO and HITS.

### Head to Head
Pick 2 to 5 loads from any cartridges in one category, for example a .308 Winchester load against a 6.5 Creedmoor load, or add them from the Load Dictionary. You see:

- every figure side by side, with the best one highlighted and how far behind the others are, in %;
- how many factors each load wins;
- each load's grade and rank from the Load Dictionary (against its own cartridge, so the two tabs always agree);
- a downrange table of velocity and energy.

On a phone this is laid out as cards: one per load, then one per factor with a bar for each load, then downrange at the distance you pick.

### Handloads
In the Load Dictionary (rifle and handgun), **+ Add handload** opens a form for your own load: bullet (pick from the built-in bullet library or type your own), powder and charge, velocity, barrel length, purpose and cost per round (a total, or bullet + powder + primer + brass with the number of times you reuse the brass). Handloads are graded alongside the factory loads, marked in a different colour, and can be edited, duplicated or deleted.

Handload figures are only as good as your data. The app does not check pressure or safety: always follow a published load manual.

### Settings
Theme (several colour schemes; Classic is the original dark look) and text size are in the sidebar on desktop and on the Settings tab on the phone. On Android, the back button steps back through the menus; on the Home screen it closes the app.

## How the grades work
For each factor, a load is scored on a curve against the typical (median) load of the same cartridge, so going further past typical earns less and less. The factor scores are spread out so that the typical load sits at 70 and one "typical spread" (median absolute deviation) moves it about 10 points, then combined using the scoring weights. Letter grades: S 85+, A 77+, B 66+, C 55+, D 45+, F below. Shotshells are only compared with the same load type (target with target, buckshot with buckshot, slugs with slugs).

- **Taylor KO**: bullet weight (gr) × velocity (fps) × diameter (in) ÷ 7000.
- **HITS** (Hornady Index of Terminal Standards): (weight² ÷ 7000) × (velocity ÷ diameter²) ÷ 100, shown with Hornady's game-size class.
- **Velocity downrange**: integrated from the G1 drag model using each load's G1 ballistic coefficient.
- **Recoil**: free recoil energy for a gun of the weight you enter.

## Download and install
Releases are on the repository's **Releases** page.

- **Windows**: run `CartridgeCalculator-Setup.exe`. It installs for the current user (no admin password), adds Start menu and desktop shortcuts, and can be removed from Settings > Apps. A newer installer upgrades in place and keeps your handloads and settings. The installer isn't code-signed, so SmartScreen may say "Windows protected your PC": click More info, then Run anyway. A portable .zip is also available.
- **Linux**: unpack and run the installer, which adds the app to your launcher. Run it again with a newer release to update (your own files are kept), or with `--uninstall` to remove it.
  ```
  tar xzf CartridgeCalculator-Linux.tar.gz
  bash CartridgeCalculator/install.sh
  ```
- **Android**: install `CartridgeCalculator.apk` (allow installs from your browser or file manager when asked).

The download files keep their old `CartridgeCalculator` names so updates install over earlier versions.

## For developers

### Repository layout
```
src/cartridge_calculator.py   desktop app (single file, Python standard library + Tkinter only)
web/template.html             phone/web app (single page, no framework)
web/build_web.py              embeds the CSV data into web/www/index.html
data/loads_*.csv              factory loads, one file per category
data/ammo_*.csv               cartridge list (cartridges with no factory loads can still hold handloads)
data/bullets.csv              bullet library for the handload form (weight, diameter, approximate G1 BC)
assets/                       app icons (drawn by scripts/make_icons.py, needs Pillow)
scripts/build_linux.sh        build and install on Fedora / Linux
scripts/install_linux.sh      installer shipped in the Linux release (as install.sh)
scripts/build_windows.bat     build the Windows .exe locally
scripts/windows_installer.iss Inno Setup script for the Windows installer (built in CI)
.github/workflows/release.yml builds Windows, Linux and Android
package.json, capacitor.config.json   Android wrapper (Capacitor)
research/                     where each added load came from
```

### Running from source
```
python3 src/cartridge_calculator.py        # desktop app (needs Tk: python3-tkinter)
python3 web/build_web.py                   # then open web/www/index.html in a browser
```
Handloads (`my_handloads.csv`) and settings (`settings.json`) are saved next to the data files and are git-ignored; the phone/web version keeps them in the browser. The desktop and web versions use the same formulas and data and must stay in step: after editing any CSV or `web/template.html`, run `python3 web/build_web.py`.

### Data files
- `loads_*.csv` columns: cartridge, load, bullet_gr, muzzle_fps, bc_g1, powder_gr, default_cost, default, source, group, barrel_in, purpose (and optionally diameter_in). Every load name starts with its brand. `barrel_in` is the test barrel length; `purpose` is Hunting / Varmint / Target / Match / Defense / Subsonic (shotguns use `group`, their load type).
- `ammo_*.csv` holds generic loads with no brand names; it provides the cartridge list.
- 5.56x45mm NATO loads are listed under .223 Remington and 7.62x51mm NATO under .308 Winchester.
- Metric cartridges are named with "mm" (7.62x39mm, 7.62x54mmR). Saved handloads and prices that use older names are matched up automatically through `RENAMED_CARTRIDGES` in `src/cartridge_calculator.py`.
- Bullet diameters for Taylor KO and HITS come from the `DIAMETERS` table in the same file.
- `bullets.csv` BCs are approximate published G1 figures.

### Making a release
```
git pull && git tag v1.6 && git push origin v1.6
```
GitHub Actions builds the Windows installer and .zip, the Linux .tar.gz and the Android APK, and publishes them as a release. The tag sets the version the apps show ("Development Build v1.6"; builds from source show "Development Build"). Running the workflow by hand (Actions tab > Run workflow) builds the files without releasing; they appear under the run's Artifacts.

A new APK installs over the old one only if every release is signed with the same key. Make one once (needs Java's `keytool`) and save it as a repository secret named `ANDROID_DEBUG_KEYSTORE` (Settings > Secrets and variables > Actions):
```
keytool -genkeypair -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
base64 -w0 debug.keystore      # paste this output as the secret's value
```
Keep `debug.keystore` somewhere safe and out of the repo. Without the secret, each APK gets a new key and testers have to uninstall the old app before installing a new one.

## License

Free software under the [MIT License](LICENSE): use, change and share it, with no warranty. Brand names identify products only; no maker sponsors or endorses this app. Third-party licenses and trademark notes are in [NOTICE.md](NOTICE.md).

**Read the [disclaimer](DISCLAIMER.md).** Figures are estimates, the powder charges are not reloading data, and the ballistic table is not for real shooting decisions.
