#!/usr/bin/env bash
# Builds and installs Cartridge Calculator as a normal app on Fedora (and most Linux).
# Run from anywhere:  bash scripts/build_linux.sh
set -e
cd "$(dirname "$0")/.."

echo "==> Installing Tk and Python tools (asks for your password)..."
sudo dnf install -y python3 python3-pip python3-tkinter binutils

echo "==> Building the app..."
python3 -m venv .buildenv
.buildenv/bin/pip install --quiet pyinstaller
.buildenv/bin/pyinstaller --onefile --windowed --name CartridgeCalculator src/cartridge_calculator.py

APPDIR="$HOME/.local/share/cartridge-calculator"
mkdir -p "$APPDIR" "$HOME/.local/share/applications"
cp dist/CartridgeCalculator "$APPDIR/"
cp data/*.csv "$APPDIR/"

cat > "$HOME/.local/share/applications/cartridge-calculator.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=In Like Flint - Load Lore
Comment=Best-value ammo calculator
Exec=$APPDIR/CartridgeCalculator
Path=$APPDIR
Terminal=false
Categories=Utility;
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Done! Search for 'In Like Flint - Load Lore' in your app launcher."
echo "Data files (editable) live in: $APPDIR"
