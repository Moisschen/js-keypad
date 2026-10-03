"""Draws the wiring plan (docs/wiring-de.svg, docs/wiring-en.svg).

The Pro Micro lies upside down in the case (components down), so it is drawn from below - the way it is seen
while soldering: USB at the top, both pin rows mirrored compared with the usual top view. Keys are push buttons
to GND; the mini keypad next to each one marks which key it is (little finger on the left, thumb key below).
KEY_PINS is the learned wiring of the keypad (mapper "Learn wiring", firmware command PINS).
The thumb stick is drawn like a PS5 hall stick module: top header GND/X/VCC, side header GND/Y/VCC, switch.
Run: python tools/make_wiring.py
"""
from pathlib import Path

TEXT = {
    'de': {
        'title': 'JS-Keypad – Verdrahtungsplan',
        'board': 'Pro Micro von UNTEN (liegt kopfüber im Gehäuse, Bauteile nach unten)',
        'fingers': ['Zeige', 'Mittel', 'Ring', 'Klein'],
        'rows': ['oben', 'Mitte', 'unten'],
        'thumbKey': 'Daumentaste',
        'gndKeys': 'GND-Sammelleitung zu allen Tasten',
        'stick': 'PS5 Hall-Effect-Stick',
        'gnd': 'GND', 'vcc': 'VCC', 'switch': 'Switch',
        'led': 'LED (optional)', 'free': 'frei',
        'note1': 'Tasten: ein Bein an den Pin, das andere an GND (⏚) – alle ⏚ sind eine Leitung. Stick: beide GND und beide VCC',
        'note2': 'anschließen. Läuft eine Stick-Richtung verkehrt herum: im Mapper „umkehren“, nicht umlöten.',
    },
    'en': {
        'title': 'JS-Keypad – wiring plan',
        'board': 'Pro Micro seen from BELOW (lies upside down in the case, components down)',
        'fingers': ['Index', 'Middle', 'Ring', 'Little'],
        'rows': ['top', 'home', 'bottom'],
        'thumbKey': 'Thumb key',
        'gndKeys': 'GND line to all keys',
        'stick': 'PS5 hall effect stick',
        'gnd': 'GND', 'vcc': 'VCC', 'switch': 'Switch',
        'led': 'LED (optional)', 'free': 'free',
        'note1': 'Keys: one leg to the pin, the other to GND (⏚) – all ⏚ are one line. Stick: connect both GND and both VCC.',
        'note2': 'If a stick direction runs the wrong way: flip it in the mapper instead of resoldering.',
    },
}

# Pro Micro header, top to bottom, seen from BELOW (mirrored): the usual right row is now on the left.
LEFT = [('RAW', None), ('GND', 'GND'), ('RST', None), ('VCC', 'VCC'), ('A3', 'A3'), ('A2', 'A2'),
        ('A1', 'A1'), ('A0', 'A0'), ('15', '15'), ('14', '14'), ('16', '16'), ('10', '10')]
RIGHT = [('TXO', '1'), ('RXI', '0'), ('GND', 'GND'), ('GND', 'GND'), ('2', '2'), ('3', '3'),
         ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ('8', '8'), ('9', '9')]

# Learned wiring: pin of each key slot (row by row top/home/bottom, each index, middle, ring, little; 12 = thumb)
KEY_PINS = ['1', '7', '5', 'A2', '3', '6', '9', 'A3', '4', '8', '0', '10', '15']
# Stick: which Pro Micro pin each stick signal goes to
STICK_PINS = {'Y': 'A1', 'X': 'A0', 'SW': '14'}

W, H = 1180, 850
TOP, PITCH = 150, 34
BX0, BX1 = 520, 670
PX_L, PX_R = 540, 650
COL = {'gnd': '#0ea5c6', 'vcc': '#dc2626', 'x': '#d4a017', 'y': '#16a34a', 'sw': '#a21caf'}


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def pin_y(i):
    return TOP + i * PITCH


def mini_keypad(x, y, slot):
    out = [f'<rect x="{x + 41}" y="{y + 17}" width="6.5" height="6.5" rx="1.3" class="{"mk on" if slot == 12 else "mk"}"/>']
    for row in range(3):
        for col in range(4):
            cls = 'mk on' if row * 4 + col == slot else 'mk'
            out.append(f'<rect x="{x + (3 - col) * 10}" y="{y + row * 8}" width="8.5" height="6.5" rx="1.3" class="{cls}"/>')
    return ''.join(out)


def ground(x, y):
    return f'<path d="M{x} {y} v6 M{x - 7} {y + 6} h14 M{x - 4.5} {y + 9.5} h9 M{x - 2} {y + 13} h4" class="gndsym"/>'


def button(a, b, y):
    m = (a + b) / 2
    return (f'<circle cx="{a + 4}" cy="{y}" r="2.6" class="term"/><circle cx="{b - 4}" cy="{y}" r="2.6" class="term"/>'
            f'<path d="M{a + 4} {y - 3} L{b - 6} {y - 10}" class="btn"/><path d="M{m} {y - 7} v-8 M{m - 6} {y - 15} h12" class="btn"/>')


def build(lang):
    T = TEXT[lang]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, system-ui, -apple-system, sans-serif">', '<style>',
         ':root{--t:#1d2330;--m:#6b7280;--w:#2563eb;--g:#4b5563;--pcb:#1e3a5f;--pcbline:#0f2440;--silk:#f1f5f9;'
         '--gold:#e6b450;--usb:#c0c6cf;--mk:#e5e7eb;--mkline:#c3c9d2;--body:#9ca3af;--bodyline:#6b7280;--hdr:#f59e0b}',
         '@media (prefers-color-scheme: dark){:root{--t:#e6e8ec;--m:#9aa3b2;--w:#60a5fa;--g:#9ca3af;--pcbline:#3b5b85;'
         '--mk:#2d3340;--mkline:#4a5263;--body:#4b5563;--bodyline:#9ca3af}}',
         'text{fill:var(--t);font-size:13px}.m{fill:var(--m)}.small{font-size:11px}.b{font-weight:600}',
         '.silk{fill:var(--silk);font-size:11px;font-weight:600}.title{font-size:18px;font-weight:700}',
         '.wk{stroke:var(--w);stroke-width:2.2;fill:none}.wg{stroke:var(--g);stroke-width:2.2;fill:none}',
         '.wo{stroke:var(--m);stroke-width:1.6;fill:none;stroke-dasharray:4 4}',
         '.term{fill:none;stroke:var(--t);stroke-width:1.6}.btn{stroke:var(--t);stroke-width:1.8;fill:none;stroke-linecap:round}',
         '.gndsym{stroke:var(--g);stroke-width:1.8;fill:none;stroke-linecap:round}',
         '.mk{fill:var(--mk);stroke:var(--mkline);stroke-width:.6}.mk.on{fill:var(--w);stroke:var(--w)}',
         '.hole{fill:var(--pcbline);stroke:var(--gold);stroke-width:2.4}',
         '.sw{fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}',
         '.tp{stroke-width:3;fill:var(--usb)}',
         '</style>',
         f'<text x="24" y="34" class="title">{esc(T["title"])}</text>']

    # --- Board (bottom side: no parts, just the pads) ---
    by0, by1 = TOP - 40, TOP + 11 * PITCH + 34
    cx = (BX0 + BX1) / 2
    o.append(f'<rect x="{BX0}" y="{by0}" width="{BX1 - BX0}" height="{by1 - by0}" rx="8" fill="var(--pcb)" stroke="var(--pcbline)" stroke-width="2"/>')
    o.append(f'<rect x="{cx - 22}" y="{by0 - 10}" width="44" height="30" rx="5" fill="var(--usb)" stroke="var(--pcbline)" stroke-width="1.5"/>')
    o.append(f'<rect x="{cx - 13}" y="{by0 - 4}" width="26" height="6" rx="3" fill="var(--pcbline)"/>')
    cy = TOP + 6.2 * PITCH
    o.append(f'<text x="{cx}" y="{cy}" class="silk" text-anchor="middle" font-size="15" transform="rotate(-90 {cx} {cy})">Pro Micro · UNTEN</text>')
    o.append(f'<text x="{cx}" y="{by1 + 22}" class="m small" text-anchor="middle">{esc(T["board"])}</text>')
    for i, (silk, _) in enumerate(LEFT):
        o.append(f'<circle cx="{PX_L}" cy="{pin_y(i)}" r="7" class="hole"/><text x="{PX_L + 13}" y="{pin_y(i) + 4}" class="silk">{silk}</text>')
    for i, (silk, _) in enumerate(RIGHT):
        o.append(f'<circle cx="{PX_R}" cy="{pin_y(i)}" r="7" class="hole"/><text x="{PX_R - 13}" y="{pin_y(i) + 4}" class="silk" text-anchor="end">{silk}</text>')

    def name_of(slot):
        if slot == 12:
            return T['thumbKey']
        row, col = divmod(slot, 4)
        return f'{T["fingers"][col]} · {T["rows"][row]}'

    def key_right(y, slot, pin):
        o.append(f'<path d="M{PX_R} {y} H{PX_R + 120}" class="wk"/>' + button(PX_R + 120, PX_R + 160, y))
        o.append(f'<path d="M{PX_R + 160} {y} H{PX_R + 176}" class="wg"/>' + ground(PX_R + 176, y))
        o.append(mini_keypad(PX_R + 196, y - 11, slot))
        o.append(f'<text x="{PX_R + 252}" y="{y + 4}" class="b">{esc(name_of(slot))}</text>')
        o.append(f'<text x="{PX_R + 14}" y="{y - 6}" class="m small">Pin {pin}</text>')

    def key_left(y, slot, pin):
        o.append(f'<path d="M{PX_L} {y} H{PX_L - 120}" class="wk"/>' + button(PX_L - 160, PX_L - 120, y))
        o.append(f'<path d="M{PX_L - 160} {y} H{PX_L - 176}" class="wg"/>' + ground(PX_L - 176, y))
        o.append(mini_keypad(PX_L - 244, y - 11, slot))
        o.append(f'<text x="{PX_L - 252}" y="{y + 4}" class="b" text-anchor="end">{esc(name_of(slot))}</text>')
        o.append(f'<text x="{PX_L - 14}" y="{y - 6}" class="m small" text-anchor="end">Pin {pin}</text>')

    # --- right row (TXO, RXI, GND, GND, 2..9) ---
    gnd_done = False
    for i, (silk, pin) in enumerate(RIGHT):
        y = pin_y(i)
        if pin in KEY_PINS:
            key_right(y, KEY_PINS.index(pin), pin)
        elif pin == 'GND' and not gnd_done:
            gnd_done = True
            o.append(f'<path d="M{PX_R} {y} H{PX_R + 176}" class="wg"/>' + ground(PX_R + 176, y))
            o.append(f'<text x="{PX_R + 196}" y="{y + 4}" class="b">{esc(T["gndKeys"])}</text>')
        elif pin == '2':
            o.append(f'<path d="M{PX_R} {y} H{PX_R + 90}" class="wo"/><text x="{PX_R + 98}" y="{y + 4}" class="m">{esc(T["led"])}</text>')
        else:
            o.append(f'<text x="{PX_R + 14}" y="{y + 4}" class="m small">{T["free"]}</text>')

    # --- left row: keys and the stick ---
    stick_rows = {}
    for i, (silk, pin) in enumerate(LEFT):
        y = pin_y(i)
        if pin in KEY_PINS:
            key_left(y, KEY_PINS.index(pin), pin)
        elif pin in ('GND', 'VCC') or pin in STICK_PINS.values():
            stick_rows[pin] = y
        else:
            o.append(f'<text x="{PX_L - 14}" y="{y + 4}" class="m small" text-anchor="end">{T["free"]}</text>')

    # Stick module below the left row (seen from the solder side, headers pointing up and to the right)
    mx0, my0, mx1, my1 = 170, 640, 350, 780
    o.append(f'<text x="{(mx0 + mx1) / 2}" y="{my1 + 26}" class="b" text-anchor="middle">{esc(T["stick"])}</text>')
    o.append(f'<rect x="{mx0}" y="{my0}" width="{mx1 - mx0}" height="{my1 - my0}" rx="10" fill="var(--body)" stroke="var(--bodyline)" stroke-width="2"/>')
    o.append(f'<circle cx="{mx0 + 110}" cy="{my0 + 75}" r="34" fill="none" stroke="var(--bodyline)" stroke-width="2.5"/>'
             f'<circle cx="{mx0 + 110}" cy="{my0 + 75}" r="15" fill="var(--bodyline)"/>')
    # top header (GND, X, VCC), side header (GND, Y, VCC), switch (Switch, GND)
    o.append(f'<rect x="{mx0 + 86}" y="{my0 - 22}" width="92" height="22" rx="4" fill="var(--hdr)"/>')
    o.append(f'<rect x="{mx0 - 22}" y="{my0 + 30}" width="22" height="78" rx="4" fill="var(--hdr)"/>')
    o.append(f'<rect x="{mx0 + 4}" y="{my0 - 16}" width="72" height="16" rx="3" fill="var(--bodyline)"/>')
    top = {'gnd': (mx0 + 100, my0 - 11), 'x': (mx0 + 132, my0 - 11), 'vcc': (mx0 + 164, my0 - 11)}
    side = {'gnd': (mx0 - 11, my0 + 43), 'y': (mx0 - 11, my0 + 69), 'vcc': (mx0 - 11, my0 + 95)}   # zur Leitungsseite hin
    swp = {'sw': (mx0 + 18, my0 - 8), 'gnd': (mx0 + 62, my0 - 8)}
    for d, below in [(top, False), (side, False), (swp, True)]:
        for k, (x, y) in d.items():
            o.append(f'<circle cx="{x}" cy="{y}" r="6" class="tp" stroke="{COL["sw" if k == "sw" else k]}"/>')
    labels = [(top['gnd'], T['gnd']), (top['x'], 'X'), (top['vcc'], T['vcc']), (swp['sw'], T['switch']), (swp['gnd'], T['gnd'])]
    for (x, y), t in labels:
        o.append(f'<text x="{x}" y="{y - 13}" class="small b" text-anchor="middle">{esc(t)}</text>')
    for (x, y), t in [(side['gnd'], T['gnd']), (side['y'], 'Y'), (side['vcc'], T['vcc'])]:
        o.append(f'<text x="{x + 18}" y="{y + 4}" class="small b">{esc(t)}</text>')

    # Wires: straight along the pin row to the left, then a smooth curve down to each stick terminal
    def wire(pin, terminals, color):
        y = stick_rows[pin]
        xa = LANE[pin]   # links an den Tastenbeschriftungen vorbei, dann hinunter zum Stick
        o.append(f'<path d="M{PX_L} {y} H{xa}" class="sw" stroke="{color}"/>')
        for tx, ty, from_side in terminals:
            if from_side:
                d = f'M{xa} {y} V{ty - 30} C{xa} {ty}, {tx - 30} {ty}, {tx - 6} {ty}'
            else:
                d = f'M{xa} {y} V{ty - 70} C{xa} {ty - 30}, {tx} {ty - 50}, {tx} {ty - 6}'
            o.append(f'<path d="{d}" class="sw" stroke="{color}"/>')
        o.append(f'<circle cx="{xa}" cy="{y}" r="3.5" fill="{color}"/>')
        o.append(f'<text x="{PX_L - 14}" y="{y - 6}" class="small b" text-anchor="end" fill="{color}">{pin}</text>')

    LANE = {'GND': 24, 'VCC': 40, STICK_PINS['Y']: 56, STICK_PINS['X']: 72, STICK_PINS['SW']: 88}
    wire('GND', [(*top['gnd'], False), (*side['gnd'], True), (*swp['gnd'], False)], COL['gnd'])
    wire('VCC', [(*top['vcc'], False), (*side['vcc'], True)], COL['vcc'])
    wire(STICK_PINS['Y'], [(*side['y'], True)], COL['y'])
    wire(STICK_PINS['X'], [(*top['x'], False)], COL['x'])
    wire(STICK_PINS['SW'], [(*swp['sw'], False)], COL['sw'])

    o.append(f'<text x="24" y="{H - 34}" class="m">{esc(T["note1"])}</text>')
    o.append(f'<text x="24" y="{H - 14}" class="m">{esc(T["note2"])}</text>')
    o.append('</svg>')
    return '\n'.join(o) + '\n'


if __name__ == '__main__':
    import hashlib
    import re
    docs = Path(__file__).resolve().parent.parent / 'docs'
    digest = hashlib.md5()
    for lang in TEXT:
        svg = build(lang)
        digest.update(svg.encode('utf-8'))
        (docs / f'wiring-{lang}.svg').write_text(svg, encoding='utf-8')
        print('wrote', docs / f'wiring-{lang}.svg')
    # Kennung im Mapper: neuer Plan -> neue Bild-URL, der Browser nimmt nicht die alte Datei aus dem Cache
    html = docs / 'index.html'
    text = html.read_text(encoding='utf-8')
    html.write_text(re.sub(r"const WIRING_V = '[^']*';", f"const WIRING_V = '{digest.hexdigest()[:8]}';", text), encoding='utf-8')
