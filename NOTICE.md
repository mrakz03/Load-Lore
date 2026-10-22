# Notices

In Like Flint - Load Lore is released under the MIT License (see LICENSE).

## Trademarks and load data

Ammunition, bullet and powder names (for example Federal, Hornady, Winchester,
Remington, Fiocchi, PMC, CCI, ELEY, Speer, Black Hills, SIG Sauer, Lapua, Norma,
Barnes, Nosler, Buffalo Bore, Underwood, Sellier & Bellot, PPU, IMI, Hodgdon, IMR,
Alliant (Reloder), Accurate, Ramshot and Vihtavuori) are trademarks of their
owners. They are used only to identify the products listed. This project is not
made, sponsored or endorsed by any of these companies.

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
