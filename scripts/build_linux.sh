#!/usr/bin/env bash
# Builds Load Lore from source and installs it as a normal app (Fedora; other distros: install
# python3, pip and Tk with your package manager first). Run from anywhere:  bash scripts/build_linux.sh
# Same files as the release build in CI, installed by the same install.sh.
set -e
cd "$(dirname "$0")/.."

if command -v dnf >/dev/null 2>&1; then
    echo "==> Installing Tk and Python tools (asks for your password)..."
    sudo dnf install -y python3 python3-pip python3-tkinter binutils
fi

echo "==> Building the app..."
python3 -m venv .buildenv
.buildenv/bin/pip install --quiet pyinstaller
.buildenv/bin/pyinstaller -y --onefile --windowed --name CartridgeCalculator --add-data "assets/icon.png:." src/cartridge_calculator.py

rm -rf build/CartridgeCalculator && mkdir -p build/CartridgeCalculator
cp dist/CartridgeCalculator data/*.csv assets/icon.png LICENSE LEGAL.md build/CartridgeCalculator/
rm -f build/CartridgeCalculator/my_*.csv
cp scripts/install_linux.sh build/CartridgeCalculator/install.sh
bash build/CartridgeCalculator/install.sh
