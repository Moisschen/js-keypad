#!/bin/bash
# Builds the firmware, copies it into the web mapper (docs/) and records its version there.
# Run this after every firmware change and bump FirmwareVersion in js_keypad.ino, then commit
# docs/ - otherwise the web mapper offers an outdated update or shows the wrong version.
set -e
cd "$(dirname "$0")"
CLI=$(ls "$USERPROFILE/arduino-cli/"arduino-cli.exe 2>/dev/null || find "$USERPROFILE/arduino-cli" -name arduino-cli.exe | head -1)
# Own USB ID (pid.codes test VID), so the mapper finds the keypad and Steam treats it as a new device.
USB_ARGS=(--build-property build.vid=0x1209 --build-property build.pid=0x0003
          --build-property 'build.usb_product="JS-Keypad"' --build-property 'build.usb_manufacturer="JS-Keypad"')

"$CLI" compile -b arduino:avr:leonardo "${USB_ARGS[@]}" --output-dir build firmware/js_keypad

cp build/js_keypad.ino.hex docs/firmware.hex
grep FirmwareVersion firmware/js_keypad/js_keypad.ino | grep -o '"[0-9][0-9.]*"' | head -1 | tr -d '"' > docs/firmware-version.txt
echo "Firmware $(cat docs/firmware-version.txt) gebaut und nach docs/ kopiert."
