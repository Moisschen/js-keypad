# JS-Keypad

12-Tasten-Keypad (4 Finger × 3 Reihen) mit Daumen-Stick für die linke Hand – Firmware für den
Pro Micro und ein Web-Mapper, in dem man auf ein Abbild des Keypads klickt und die Taste belegt.

**Mapper:** https://moisschen.github.io/js-keypad/ (Chrome oder Edge, Web Serial)

inspired by [Jasp](https://github.com/multifex/prototypes/tree/main/jasp-keyboard-joystick)

## Funktionen

- Klickbares Abbild: Taste anklicken (oder am Keypad drücken) → gewünschte Taste auf der PC-Tastatur
  drücken oder aus der Liste wählen. Wird sofort auf dem Keypad gespeichert.
- Belegungen sind HID-Tastencodes – gleiche physische Taste auf jedem Tastaturlayout (QWERTZ, AZERTY …),
  die Beschriftung im Mapper folgt dem Layout des PCs.
- Stick als Tastatur (Standard W/A/S/D + Shift), Controller oder Maus; Kalibrierung, Stickwinkel.
- Tastentest, Verdrahtungs-Check, Sichern/Laden der Einstellungen.
- Firmware direkt aus dem Browser aufspielen (auch auf einen neuen Pro Micro).

## Verdrahtung

Jede Taste zwischen Pin und GND, keine Dioden/Matrix (`INPUT_PULLUP`):

|        | Zeige | Mittel | Ring | Klein |
|--------|-------|--------|------|-------|
| oben   | 0     | 1      | 3    | 4     |
| Mitte  | 5     | 6      | 7    | 8     |
| unten  | 9     | 10     | A2   | A3    |

Stick: VRx → A1, VRy → A0, SW → 14 (oder 16), dazu VCC und GND. Pin 15 = Kalibrier-Taster (optional),
Pin 2 = LED (optional).

## Rettung

Stick-Klick beim Einstecken **3 Sekunden halten** → Bootloader, dann im Mapper „2. Firmware aufspielen“.
Kurz klicken beim Einstecken schaltet den Stick-Modus weiter; Stick beim Einstecken hoch/rechts/runter
halten wählt Tastatur/Controller/Maus direkt.

## Bauen

```bash
./build.sh
```

Braucht `arduino-cli` mit `arduino:avr`. Baut `firmware/js_keypad`, kopiert das Hex nach `docs/` und
schreibt die Version nach `docs/firmware-version.txt`. Vor jedem Release `FirmwareVersion` in
`js_keypad.ino` hochzählen und `docs/` mit committen – GitHub Pages liefert den Mapper aus `docs/`.
