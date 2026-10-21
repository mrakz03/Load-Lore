# Cartridge Value Calculator

Grades ammo from S to F on velocity, energy, recoil and price, with Taylor KO and HITS shown for rifle and handgun loads. There is a desktop app (Python/Tkinter, Windows and Linux) and a phone/web version (installable as an Android APK).

Two ways to compare (both in the sidebar):
- **Compare Cartridges**: which caliber is the best value, graded against the whole category.
- **Compare Loads**: which brand or load of one cartridge is best, filterable by purpose (hunting, target, match, defense...). Reloaders can add their own handloads (bullet, powder, charge, velocity, cost per round), see them graded against factory ammo, and edit or delete them.

## Repository layout
```
src/cartridge_calculator.py   desktop app (single file, standard library only)
data/ammo_*.csv               general cartridge data (Compare Cartridges)
data/loads_*.csv              per-manufacturer loads (Compare Loads)
data/bullets.csv              common bullets (weight, diameter, approximate G1 BC) for the handload form
web/template.html             phone/web app (single page)
web/build_web.py              embeds the CSV data into web/www/index.html
scripts/build_linux.sh        build and install on Fedora/Linux
scripts/build_windows.bat     build the Windows .exe locally
.github/workflows/release.yml builds Windows, Linux and Android in CI
package.json, capacitor.config.json   Android wrapper (Capacitor)
```

## Running from source
```
python3 src/cartridge_calculator.py        # desktop app (needs Tk: python3-tkinter)
python3 web/build_web.py                   # then open web/www/index.html in a browser
```
Your own calibers (`my_calibers.csv`), handloads (`my_handloads.csv`) and settings (`settings.json`) are saved in `data/` and are git-ignored. On the phone/web version they are kept in the browser.

## Making a release
```
git tag v1.0 && git push origin v1.0
```
Download the Windows .zip, Linux .tar.gz and Android .apk from the repo's Releases page. Running the workflow by hand (Actions tab, Run workflow) builds them without releasing.

## Data notes
- `loads_*.csv` columns: cartridge, load, bullet_gr, muzzle_fps, bc_g1, powder_gr, default_cost, default, source, group, barrel_in, purpose. `barrel_in` (test barrel length) and `purpose` (Hunting / Varmint / Target / Match / Defense / Subsonic; shotguns use their load type) are optional, as is `diameter_in`.
- Loads come from the 2026 Hornady, ELEY, Fiocchi, Winchester, Remington, PMC, Federal and CCI catalogs, plus Speer Gold Dot / Lawman from speer.com. Prices and powder charges are estimates.
- `bullets.csv` BCs are approximate published G1 figures; edit them (or type your own in the form) if you know better. Handload figures are only as good as your data: always follow published load manuals.
- Cartridges beyond the core list come from the Hornady catalog; a few popular ones with no catalog data (7.62x54R, 5.45x39, 7.62x25, .38 Super, .32 S&W Long) use typical factory figures, marked as such.
- 5.56 NATO loads are listed under .223 Remington and 7.62x51 NATO under .308 Winchester.
- After editing any CSV or `web/template.html`, run `python3 web/build_web.py`.

## Taylor KO and HITS
Every rifle and handgun result shows the Taylor Knock-Out factor (bullet weight × velocity × diameter ÷ 7000) and Hornady's HITS index ((weight² ÷ 7000) × (velocity ÷ diameter²) ÷ 100), calculated at the distance you pick. Both start at weight 0 in the grade, so raise them under "Scoring weights" if you want them to count. Bullet diameters come from the `DIAMETERS` table in `src/cartridge_calculator.py`; custom calibers can supply their own. Shotshells don't show them.
