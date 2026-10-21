#!/usr/bin/env bash
# Installs a downloaded Linux release as a normal app (no building needed).
# Unpack CartridgeCalculator-Linux.tar.gz, then run:   bash CartridgeCalculator/install.sh
# Run it again with a newer release to update; your handloads, calibers and settings are kept.
# To remove the app:   bash install.sh --uninstall
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
APPDIR="$HOME/.local/share/cartridge-calculator"
DESKTOP="$HOME/.local/share/applications/cartridge-calculator.desktop"
USER_FILES="my_calibers.csv my_handloads.csv settings.json"

if [ "$1" = "--uninstall" ]; then
    rm -f "$DESKTOP"
    if [ -d "$APPDIR" ]; then
        for f in "$APPDIR"/*; do
            case " $USER_FILES " in *" $(basename "$f") "*) ;; *) rm -rf "$f" ;; esac
        done
        rmdir "$APPDIR" 2>/dev/null || echo "Kept your own files in $APPDIR (delete the folder to remove them)."
    fi
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "Cartridge Calculator removed."
    exit 0
fi

if [ ! -f "$SRC/CartridgeCalculator" ]; then
    echo "Run this from the unpacked CartridgeCalculator folder (CartridgeCalculator program not found next to it)."
    exit 1
fi

mkdir -p "$APPDIR" "$(dirname "$DESKTOP")"
# clear the data files an older version shipped, so ones a release drops don't linger
rm -f "$APPDIR"/ammo_*.csv "$APPDIR"/loads_*.csv "$APPDIR"/bullets.csv
cp "$SRC/CartridgeCalculator" "$APPDIR/"
cp "$SRC"/*.csv "$APPDIR/"
[ -f "$SRC/icon.png" ] && cp "$SRC/icon.png" "$APPDIR/"
chmod +x "$APPDIR/CartridgeCalculator"

cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=Cartridge Calculator
Comment=Best-value ammo calculator
Exec=$APPDIR/CartridgeCalculator
Path=$APPDIR
Icon=$APPDIR/icon.png
Terminal=false
Categories=Utility;
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Done! Search for 'Cartridge Calculator' in your app launcher."
echo "Data files (editable) live in: $APPDIR"
