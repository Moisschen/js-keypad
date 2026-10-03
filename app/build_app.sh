#!/bin/bash
# Baut "JS-Keypad Profile.exe" (Tray-Umschalter + mitgelieferter Web-Mapper aus ../docs).
# Vorher: python -m pip install pyserial psutil pystray pillow pyinstaller
set -e
cd "$(dirname "$0")"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "JS-Keypad Profile" --icon icon.ico \
  --add-data "../docs;docs" --add-data "tray.png;." --add-data "tray-active.png;." jskeypad_profile.py
echo "Fertig: app/dist/JS-Keypad Profile.exe"
