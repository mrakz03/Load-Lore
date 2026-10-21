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
scripts/install_linux.sh      installs a downloaded Linux release (shipped in the tar as install.sh)
scripts/build_windows.bat     build the Windows .exe locally
scripts/windows_installer.iss Inno Setup script for the Windows installer (built in CI)
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
The tag sets the version number the apps show (`v1.5` shows as "Development Build v1.5"; builds from source show "Development Build").

Download the Windows installer (`CartridgeCalculator-Setup.exe`) or .zip, Linux .tar.gz and Android .apk from the repo's Releases page. Running the workflow by hand (Actions tab, Run workflow) builds them without releasing.

On Android, a new APK installs over the old one only if every release is signed with the same key. Make one once (needs Java's `keytool`) and save it as a repository secret named `ANDROID_DEBUG_KEYSTORE` (Settings > Secrets and variables > Actions):
```
keytool -genkeypair -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
base64 -w0 debug.keystore      # paste this output as the secret's value
```
Keep `debug.keystore` somewhere safe and out of the repo. Without the secret, each APK gets a new key, so testers have to uninstall the old app before installing a new one.

On Windows, double-click `CartridgeCalculator-Setup.exe`. It installs for the current user (no admin password), adds Start menu and desktop shortcuts, and can be removed from Settings > Apps. Running a newer installer upgrades in place and keeps your handloads and settings. The installer isn't code-signed, so Windows SmartScreen may say "Windows protected your PC": click More info, then Run anyway.

To install the Linux release, unpack it and run the installer; it adds the app to your launcher. Run it again with a newer release to update (your own files are kept), or with `--uninstall` to remove it.
```
tar xzf CartridgeCalculator-Linux.tar.gz
bash CartridgeCalculator/install.sh
```

## Data notes
- `loads_*.csv` columns: cartridge, load, bullet_gr, muzzle_fps, bc_g1, powder_gr, default_cost, default, source, group, barrel_in, purpose. `barrel_in` (test barrel length) and `purpose` (Hunting / Varmint / Target / Match / Defense / Subsonic; shotguns use their load type) are optional, as is `diameter_in`.
- Loads come from the 2026 Hornady, ELEY, Fiocchi, Winchester, Remington, PMC, Federal and CCI catalogs, plus Speer Gold Dot / Lawman from speer.com. Prices and powder charges are estimates.
- `bullets.csv` BCs are approximate published G1 figures; edit them (or type your own in the form) if you know better. Handload figures are only as good as your data: always follow published load manuals.
- Cartridges beyond the core list come from the Hornady catalog; a few popular ones with no catalog data (7.62x54mmR, 5.45x39mm, 7.62x25mm Tokarev, .38 Super, .32 S&W Long) use typical factory figures, marked as such.
- 5.56x45mm NATO loads are listed under .223 Remington and 7.62x51mm NATO under .308 Winchester.
- Metric cartridges are named with "mm" (7.62x39mm, 7.62x54mmR). Saved handloads, calibers and prices that use the older names (7.62x39, 7.62x54R) are matched up automatically; the old-to-new list is `RENAMED_CARTRIDGES` in `src/cartridge_calculator.py`.
- After editing any CSV or `web/template.html`, run `python3 web/build_web.py`.

## Taylor KO and HITS
Every rifle and handgun result shows the Taylor Knock-Out factor (bullet weight × velocity × diameter ÷ 7000) and Hornady's HITS index ((weight² ÷ 7000) × (velocity ÷ diameter²) ÷ 100), calculated at the distance you pick. Both count toward the grade (weight 3, like velocity, energy and cost); change that under "Scoring weights". Bullet diameters come from the `DIAMETERS` table in `src/cartridge_calculator.py`; custom calibers can supply their own. Shotshells don't show them.
