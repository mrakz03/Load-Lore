# Legal

In Like Flint - Load Lore is free software under the MIT License (see LICENSE).
This page covers the disclaimer, trademarks, where the load data comes from, and
the licenses of the software bundled in the release builds.

## Disclaimer

In Like Flint - Load Lore is a hobby tool for comparing published ammunition
figures. Read this before relying on anything it shows.

- **Figures are estimates.** Velocities are makers' published numbers from test
  barrels and will differ in your firearm. Ballistic coefficients, prices and
  powder charges are often approximate. The ballistic table is a simple
  estimate in standard sea-level air, not a ballistic solver, and is not for
  sighting in, range estimation or hunting shot decisions.
- **Not reloading data.** The app does not check pressure or safety. Powder
  charges shown are not load data. Handload figures are only what you type in.
  Always confirm with the manufacturer's data and a current load manual before
  shooting or reloading.
- **Grades are opinions.** S to F grades compare loads of the same cartridge on
  a few numbers. They say nothing about accuracy, reliability, legality or
  suitability for hunting, defence or any other use.
- **No endorsement.** Brand names identify products only. No maker has
  reviewed, sponsored or endorsed this app, and none is
  affiliated with its creator.
- **Your responsibility.** Follow firearm safety rules and the law where you
  live. The authors accept no liability for any injury, damage or loss from
  using this software or its data. See the "AS IS" clause in LICENSE.

## Trademarks and load data

Ammunition, bullet and powder names (for example Federal, Hornady, Winchester,
Remington, Fiocchi, PMC, CCI, ELEY, Speer, Black Hills, SIG Sauer, Lapua, Norma,
Barnes, Nosler, Buffalo Bore, Underwood, Sellier & Bellot, PPU, IMI, Hodgdon, IMR,
Alliant (Reloder), Accurate, Ramshot and Vihtavuori) are trademarks of their
owners. They are used only to identify the products listed. This project is not
made, sponsored or endorsed by any of these companies, and none of them is
affiliated with its creator.

Bullet weights and muzzle velocities are the makers' published figures, taken
from their 2026 catalogs, websites and retailer listings and entered by hand as facts.
Ballistic coefficients marked "partial" or "approx", prices and powder charges
are estimates made for this app. No catalog text, photos or logos are included.

## Third-party software in the release builds

The source code uses only the Python standard library. The release builds bundle:

| Component | Used in | License |
|---|---|---|
| Python runtime | Windows .exe, Linux build (via PyInstaller) | PSF License 2.0 |
| Tcl/Tk (Tkinter) | Windows .exe, Linux build | Tcl/Tk license (BSD-style) |
| PyInstaller bootloader | Windows .exe, Linux build | GPL 2.0 with a bootloader exception that allows any license for the bundled app |
| Inno Setup | Windows installer (Setup.exe) | Inno Setup license (free, permissive) |
| Capacitor (@capacitor/core, android, app, cli) | Android APK | MIT |
| AndroidX and other Android libraries pulled in by Capacitor | Android APK | Apache 2.0 |

The app icon is drawn by scripts/make_icons.py with the Inter (SIL Open Font
License 1.1) or DejaVu Sans (Bitstream Vera / public domain) font; drawing
letters into an image is allowed by both.
