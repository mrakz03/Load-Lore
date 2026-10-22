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
    echo "In Like Flint - Load Lore removed."
    exit 0
fi

if [ ! -f "$SRC/CartridgeCalculator" ] || ! ls "$SRC"/loads_*.csv >/dev/null 2>&1; then
    echo "Run this from the unpacked CartridgeCalculator folder (the program or its data files are not next to it)."
    exit 1
fi

mkdir -p "$APPDIR" "$(dirname "$DESKTOP")"
# Copy the program under a temporary name and move it into place: copying straight over it
# fails ("Text file busy") while the app is open, and the update used to stop there after
# the old data files were already deleted, leaving the app with no data.
cp "$SRC/CartridgeCalculator" "$APPDIR/CartridgeCalculator.new"
chmod +x "$APPDIR/CartridgeCalculator.new"
mv -f "$APPDIR/CartridgeCalculator.new" "$APPDIR/CartridgeCalculator"
# clear the data files an older version shipped, so ones a release drops don't linger
rm -f "$APPDIR"/ammo_*.csv "$APPDIR"/loads_*.csv "$APPDIR"/bullets.csv
cp "$SRC"/*.csv "$APPDIR/"
if [ -f "$SRC/icon.png" ]; then cp "$SRC/icon.png" "$APPDIR/"; fi

cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=In Like Flint - Load Lore
Comment=Best-value ammo calculator
Exec=$APPDIR/CartridgeCalculator
Path=$APPDIR
Icon=$APPDIR/icon.png
Terminal=false
Categories=Utility;
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if pgrep -f "$APPDIR/CartridgeCalculator" >/dev/null 2>&1; then
    echo "The app is open: close it and start it again to use the new version."
fi
echo "Done! Search for 'In Like Flint - Load Lore' in your app launcher."
echo "Data files (editable) live in: $APPDIR"
