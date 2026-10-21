# Cartridge Value Calculator

Grades ammo (S-F) by velocity, energy, recoil and price. Desktop (Python/Tkinter) and phone (web/Android) versions.

- `cartridge_calculator.py` + `ammo_*.csv`: the desktop app and its data
- `web_template.html` + `build_web.py`: the phone/web version. After editing a CSV run `python3 build_web.py`
- `.github/workflows/release.yml`: builds Windows, Linux and Android and attaches them to a Release
