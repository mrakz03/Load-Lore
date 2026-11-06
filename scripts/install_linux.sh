#!/usr/bin/env bash
# Installs a downloaded Linux release as a normal app (no building needed).
# Unpack LoadLore-v<version>-Linux.tar.gz, then run:   bash LoadLore/install.sh
# Run it again with a newer release to update; your handloads, calibers and settings are kept.
# To remove the app:   bash install.sh --uninstall
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
APPDIR="$HOME/.local/share/load-lore"
DESKTOP="$HOME/.local/share/applications/load-lore.desktop"
# where it went before the rename (Oct 2026): moved to APPDIR, your own files with it
OLD_APPDIR="$HOME/.local/share/cartridge-calculator"
OLD_DESKTOP="$HOME/.local/share/applications/cartridge-calculator.desktop"
USER_FILES="my_calibers.csv my_handloads.csv settings.json"

if [ "$1" = "--uninstall" ]; then
    rm -f "$DESKTOP" "$OLD_DESKTOP"
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

if [ ! -f "$SRC/LoadLore" ] || ! ls "$SRC"/loads_*.csv >/dev/null 2>&1; then
    echo "Run this from the unpacked LoadLore folder (the program or its data files are not next to it)."
    exit 1
fi

mkdir -p "$APPDIR" "$(dirname "$DESKTOP")"
# an install from before the rename: bring your own files over, then remove the old copy
if [ -d "$OLD_APPDIR" ] && [ "$(cd "$OLD_APPDIR" && pwd -P)" != "$(cd "$APPDIR" && pwd -P)" ]; then
    for f in $USER_FILES; do
        if [ -f "$OLD_APPDIR/$f" ] && [ ! -f "$APPDIR/$f" ]; then cp -p "$OLD_APPDIR/$f" "$APPDIR/$f"; fi
    done
    rm -rf "$OLD_APPDIR"
    rm -f "$OLD_DESKTOP"
    echo "Moved Load Lore from $OLD_APPDIR to $APPDIR (your handloads and settings came along)."
fi
# Copy the program under a temporary name and move it into place: copying straight over it
# fails ("Text file busy") while the app is open, and the update used to stop there after
# the old data files were already deleted, leaving the app with no data.
cp "$SRC/LoadLore" "$APPDIR/LoadLore.new"
chmod +x "$APPDIR/LoadLore.new"
mv -f "$APPDIR/LoadLore.new" "$APPDIR/LoadLore"
# clear the data files an older version shipped, so ones a release drops don't linger
rm -f "$APPDIR"/ammo_*.csv "$APPDIR"/loads_*.csv "$APPDIR"/bullets.csv
cp "$SRC"/*.csv "$APPDIR/"
if [ -f "$SRC/icon.png" ]; then cp "$SRC/icon.png" "$APPDIR/"; fi
rm -f "$APPDIR"/NOTICE.md "$APPDIR"/DISCLAIMER.md   # combined into LEGAL.md
for f in LICENSE LEGAL.md; do if [ -f "$SRC/$f" ]; then cp "$SRC/$f" "$APPDIR/"; fi; done

cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=Load Lore
Comment=Best-value ammo calculator
Exec=$APPDIR/LoadLore
Path=$APPDIR
Icon=$APPDIR/icon.png
Terminal=false
Categories=Utility;
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if pgrep -f "$APPDIR/LoadLore" >/dev/null 2>&1; then
    echo "The app is open: close it and start it again to use the new version."
fi
echo "Done! Search for 'Load Lore' in your app launcher."
echo "Data files (editable) live in: $APPDIR"
