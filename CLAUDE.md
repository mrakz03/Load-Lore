# Cartridge Calculator

Grades ammo S–F on velocity, energy, recoil, cost (plus Taylor KO, weight 0 by default).
HITS was removed on purpose; don't add it back.
Desktop app: src/cartridge_calculator.py (Tkinter, stdlib only). Phone/web: web/template.html,
built by `python3 web/build_web.py` into web/www (Capacitor wraps it as an APK in CI).

## Rules
- Desktop and web scoring must stay in parity (same formulas, same data).
- Data lives in data/*.csv. After editing any CSV or the template, rebuild the web version.
- Compare Cartridges grades on an absolute curve; Compare Loads grades relative to the
  same cartridge and purpose (median/MAD, centre 70).
- Handloads: my_handloads.csv (desktop) / localStorage (web). Never commit user files
  (my_calibers.csv, my_handloads.csv, settings.json).
- bullets.csv BCs are approximate; load figures are estimates; no safety validation of reloads.
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
  catalogue, so many small cartridges list only Hornady loads. Other brands could be added.

## Known to-dos
- Desktop layout fixed for HiDPI and checked under Xvfb; confirm on the real Fedora and
  Windows machines.
- Typical-figure cartridges (7.62x54R, 5.45x39, 7.62x25, .38 Super, .32 S&W Long) need verification.
