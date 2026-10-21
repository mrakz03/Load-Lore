# Cartridge Calculator

Grades ammo S–F on velocity, energy, recoil, cost (plus Taylor KO and HITS, weight 0 by default).
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

## Release
git tag vX.Y && git push origin vX.Y  → GitHub Actions builds Windows, Linux, Android.

## Known to-dos
- Desktop layout was only tested with a sandbox Tk build; check real Fedora/Windows rendering.
- Typical-figure cartridges (7.62x54R, 5.45x39, 7.62x25, .38 Super, .32 S&W Long) need verification.

Notes from Claude Sonnet 5.5
