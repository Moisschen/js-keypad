"""Draws the wiring plan (docs/wiring-de.svg, docs/wiring-en.svg).

Pro Micro seen from the top (components up, USB at the top). Every pin gets a straight wire
to what is connected to it, so no wires cross. A key is a push button to GND; the mini keypad
next to it marks which key it is (little finger on the left, like on the keypad).
Run: python tools/make_wiring.py
"""
from pathlib import Path

TEXT = {
    'de': {
        'title': 'JS-Keypad – Verdrahtungsplan',
        'board': 'Pro Micro · Draufsicht, USB oben',
        'fingers': ['Zeige', 'Mittel', 'Ring', 'Klein'],
        'rows': ['oben', 'Mitte', 'unten'],
        'gndKeys': 'GND-Sammelleitung zu allen Tasten',
        'stick': 'Daumen-Stick',
        'vcc': 'VCC (+5 V)', 'gnd': 'GND', 'sw': 'SW (Klick)',
        'led': 'LED (optional, mit Vorwiderstand)', 'thumbKey': 'Daumentaste',
        'alt': 'alternativ für SW', 'free': 'frei',
        'note1': 'Jede Taste: ein Bein an ihren Pin, das andere an GND (⏚). Alle ⏚ sind dieselbe Leitung –',
        'note2': 'einfach ein Draht von Taste zu Taste und weiter an einen GND-Pin. Keine Dioden nötig.',
    },
    'en': {
        'title': 'JS-Keypad – wiring plan',
        'board': 'Pro Micro · top view, USB up',
        'fingers': ['Index', 'Middle', 'Ring', 'Little'],
        'rows': ['top', 'home', 'bottom'],
        'gndKeys': 'GND line to all keys',
        'stick': 'Thumb stick',
        'vcc': 'VCC (+5 V)', 'gnd': 'GND', 'sw': 'SW (click)',
        'led': 'LED (optional, with resistor)', 'thumbKey': 'Thumb key',
        'alt': 'alternative for SW', 'free': 'free',
        'note1': 'Each key: one leg to its pin, the other to GND (⏚). All ⏚ are the same line –',
        'note2': 'just run one wire from key to key and on to a GND pin. No diodes needed.',
    },
}

# Pro Micro header, top to bottom. (silkscreen, Arduino pin)
LEFT = [('TXO', '1'), ('RXI', '0'), ('GND', None), ('GND', None), ('2', '2'), ('3', '3'),
        ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ('8', '8'), ('9', '9')]
RIGHT = [('RAW', None), ('GND', None), ('RST', None), ('VCC', None), ('A3', 'A3'), ('A2', 'A2'),
         ('A1', 'A1'), ('A0', 'A0'), ('15', '15'), ('14', '14'), ('16', '16'), ('10', '10')]

# Key slots: row * 4 + column (column 0 = index ... 3 = little finger), same as the firmware.
KEY_PINS = ['0', '1', '3', '4', '5', '6', '7', '8', '9', '10', 'A2', 'A3', '15']  # 12 = thumb key

W, H = 1000, 640
TOP, PITCH = 128, 34
BX0, BX1 = 425, 575        # board edges
PX_L, PX_R = 445, 555      # pin holes
STICK_X0, STICK_X1 = 872, 975


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def mini_keypad(x, y, slot):
    """4x3 key icon, little finger on the left; the given slot is filled."""
    out = []
    # thumb key: small key below the grid, right (stick side)
    cls = 'mk on' if slot == 12 else 'mk'
    out.append(f'<rect x="{x + 41}" y="{y + 17}" width="6.5" height="6.5" rx="1.3" class="{cls}"/>')
    for row in range(3):
        for col in range(4):
            vis_col = 3 - col  # draw little finger left
            cls = 'mk on' if row * 4 + col == slot else 'mk'
            out.append(f'<rect x="{x + vis_col * 10}" y="{y + row * 8}" width="8.5" height="6.5" rx="1.3" class="{cls}"/>')
    return ''.join(out)


def ground(x, y):
    return (f'<path d="M{x} {y} v6 M{x - 7} {y + 6} h14 M{x - 4.5} {y + 9.5} h9 M{x - 2} {y + 13} h4" class="gndsym"/>')


def button(x0, x1, y):
    """Push button between x0 and x1 on a wire at y (open contact with a plunger)."""
    a, b = min(x0, x1), max(x0, x1)
    return (f'<circle cx="{a + 4}" cy="{y}" r="2.6" class="term"/><circle cx="{b - 4}" cy="{y}" r="2.6" class="term"/>'
            f'<path d="M{a + 4} {y - 3} L{b - 6} {y - 10}" class="btn"/>'
            f'<path d="M{(a + b) / 2} {y - 7} v-8 M{(a + b) / 2 - 6} {y - 15} h12" class="btn"/>')


def build(lang):
    T = TEXT[lang]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, system-ui, -apple-system, sans-serif">',
         '<style>',
         ':root{--t:#1d2330;--m:#6b7280;--w:#2563eb;--s:#d97706;--g:#4b5563;--v:#dc2626;--o:#9ca3af;--pcb:#1e3a5f;'
         '--pcbline:#0f2440;--silk:#f1f5f9;--gold:#e6b450;--usb:#c0c6cf;--mk:#e5e7eb;--mkline:#c3c9d2;--box:#f8fafc;--boxline:#cbd5e1}',
         '@media (prefers-color-scheme: dark){:root{--t:#e6e8ec;--m:#9aa3b2;--w:#60a5fa;--s:#fbbf24;--g:#9ca3af;'
         '--v:#f87171;--o:#6b7280;--pcb:#1e3a5f;--pcbline:#3b5b85;--mk:#2d3340;--mkline:#4a5263;--box:#1b1f27;--boxline:#3a4250}}',
         'text{fill:var(--t);font-size:13px}.m{fill:var(--m)}.small{font-size:11px}.b{font-weight:600}',
         '.silk{fill:var(--silk);font-size:11px;font-weight:600}.title{font-size:18px;font-weight:700}',
         '.wk{stroke:var(--w);stroke-width:2.2;fill:none}.ws{stroke:var(--s);stroke-width:2.2;fill:none}',
         '.wg{stroke:var(--g);stroke-width:2.2;fill:none}.wv{stroke:var(--v);stroke-width:2.2;fill:none}',
         '.wo{stroke:var(--o);stroke-width:1.6;fill:none;stroke-dasharray:4 4}',
         '.term{fill:none;stroke:var(--t);stroke-width:1.6}.btn{stroke:var(--t);stroke-width:1.8;fill:none;stroke-linecap:round}',
         '.gndsym{stroke:var(--g);stroke-width:1.8;fill:none;stroke-linecap:round}',
         '.mk{fill:var(--mk);stroke:var(--mkline);stroke-width:.6}.mk.on{fill:var(--w);stroke:var(--w)}',
         '.hole{fill:var(--pcbline);stroke:var(--gold);stroke-width:2.4}',
         '.box{fill:var(--box);stroke:var(--boxline);stroke-width:1.2}',
         '</style>']
    o.append(f'<text x="24" y="34" class="title">{esc(T["title"])}</text>')

    # Board
    by0, by1 = TOP - 40, TOP + 11 * PITCH + 34
    o.append(f'<rect x="{BX0}" y="{by0}" width="{BX1 - BX0}" height="{by1 - by0}" rx="8" fill="var(--pcb)" stroke="var(--pcbline)" stroke-width="2"/>')
    o.append(f'<rect x="{(BX0 + BX1) / 2 - 22}" y="{by0 - 10}" width="44" height="30" rx="5" fill="var(--usb)" stroke="var(--pcbline)" stroke-width="1.5"/>')
    o.append(f'<rect x="{(BX0 + BX1) / 2 - 13}" y="{by0 - 4}" width="26" height="6" rx="3" fill="var(--pcbline)"/>')
    o.append(f'<rect x="{(BX0 + BX1) / 2 - 24}" y="{TOP + 3.5 * PITCH}" width="48" height="48" rx="3" fill="#111827" transform="rotate(45 {(BX0 + BX1) / 2} {TOP + 3.5 * PITCH + 24})"/>')
    cy = TOP + 7.6 * PITCH
    o.append(f'<text x="{(BX0 + BX1) / 2}" y="{cy}" class="silk" text-anchor="middle" font-size="15" transform="rotate(-90 {(BX0 + BX1) / 2} {cy})">Pro Micro</text>')
    o.append(f'<text x="{(BX0 + BX1) / 2}" y="{by1 + 22}" class="m small" text-anchor="middle">{esc(T["board"])}</text>')

    def pin_y(i):
        return TOP + i * PITCH

    for i, (silk, _) in enumerate(LEFT):
        y = pin_y(i)
        o.append(f'<circle cx="{PX_L}" cy="{y}" r="7" class="hole"/>')
        o.append(f'<text x="{PX_L + 13}" y="{y + 4}" class="silk">{silk}</text>')
    for i, (silk, _) in enumerate(RIGHT):
        y = pin_y(i)
        o.append(f'<circle cx="{PX_R}" cy="{y}" r="7" class="hole"/>')
        o.append(f'<text x="{PX_R - 13}" y="{y + 4}" class="silk" text-anchor="end">{silk}</text>')

    def key_entry(side, y, slot, pin_label):
        row, col = divmod(slot, 4)
        name = T['thumbKey'] if slot == 12 else f'{T["fingers"][col]} · {T["rows"][row]}'
        if side == 'L':
            o.append(f'<path d="M{PX_L} {y} H{318}" class="wk"/>')
            o.append(button(278, 318, y))
            o.append(f'<path d="M278 {y} H262" class="wg"/>' + ground(262, y))
            o.append(mini_keypad(24, y - 11, slot))
            o.append(f'<text x="72" y="{y + 4}" class="b">{esc(name)}</text>')
            o.append(f'<text x="{BX0 - 10}" y="{y - 6}" class="m small" text-anchor="end">{pin_label}</text>')
        else:
            o.append(f'<path d="M{PX_R} {y} H{640}" class="wk"/>')
            o.append(button(640, 680, y))
            o.append(f'<path d="M680 {y} H696" class="wg"/>' + ground(696, y))
            o.append(mini_keypad(716, y - 11, slot))
            o.append(f'<text x="764" y="{y + 4}" class="b">{esc(name)}</text>')
            o.append(f'<text x="{BX1 + 10}" y="{y - 6}" class="m small">{pin_label}</text>')

    def text_entry(side, y, text, cls, wire_end=None, label_cls='m'):
        if side == 'L':
            end = wire_end or 300
            o.append(f'<path d="M{PX_L} {y} H{end}" class="{cls}"/>')
            o.append(f'<text x="{end - 8}" y="{y + 4}" class="{label_cls}" text-anchor="end">{esc(text)}</text>')
        else:
            end = wire_end or 700
            o.append(f'<path d="M{PX_R} {y} H{end}" class="{cls}"/>')
            o.append(f'<text x="{end + 8}" y="{y + 4}" class="{label_cls}">{esc(text)}</text>')

    # Left header
    for i, (silk, pin) in enumerate(LEFT):
        y = pin_y(i)
        if pin in KEY_PINS:
            key_entry('L', y, KEY_PINS.index(pin), f'Pin {pin}')
        elif silk == 'GND' and i == 2:
            o.append(f'<path d="M{PX_L} {y} H262" class="wg"/>' + ground(262, y))
            o.append(f'<text x="240" y="{y + 4}" class="b" text-anchor="end">{esc(T["gndKeys"])}</text>')
        elif pin == '2':
            text_entry('L', y, T['led'], 'wo', 330)
        else:
            o.append(f'<text x="{BX0 - 10}" y="{y + 4}" class="m small" text-anchor="end">{T["free"]}</text>')

    # Right header: keys, optional pins and the stick
    stick_rows = {'GND': 1, 'VCC': 3, 'A1': 6, 'A0': 7, '14': 9}
    sy0, sy1 = pin_y(1) - 18, pin_y(9) + 18
    o.append(f'<rect x="{STICK_X0}" y="{sy0}" width="{STICK_X1 - STICK_X0}" height="{sy1 - sy0}" rx="10" class="box"/>')
    o.append(f'<circle cx="{(STICK_X0 + STICK_X1) / 2 + 12}" cy="{(sy0 + sy1) / 2}" r="26" fill="none" stroke="var(--boxline)" stroke-width="2"/>')
    o.append(f'<circle cx="{(STICK_X0 + STICK_X1) / 2 + 12}" cy="{(sy0 + sy1) / 2}" r="12" fill="var(--s)" opacity=".8"/>')
    o.append(f'<text x="{(STICK_X0 + STICK_X1) / 2}" y="{sy0 - 8}" class="b" text-anchor="middle">{esc(T["stick"])}</text>')
    stick_labels = {'GND': (T['gnd'], 'wg'), 'VCC': (T['vcc'], 'wv'), 'A1': ('VRx', 'ws'), 'A0': ('VRy', 'ws'), '14': (T['sw'], 'ws')}
    for i, (silk, pin) in enumerate(RIGHT):
        y = pin_y(i)
        key = pin if pin else silk
        if i in stick_rows.values() and key in stick_labels:
            label, cls = stick_labels[key]
            o.append(f'<path d="M{PX_R} {y} H{STICK_X0}" class="{cls}"/>')
            o.append(f'<circle cx="{STICK_X0}" cy="{y}" r="3" fill="var(--t)"/>')
            o.append(f'<text x="{STICK_X0 - 8}" y="{y - 6}" class="small b" text-anchor="end">{esc(label)}</text>')
        elif pin in KEY_PINS:
            key_entry('R', y, KEY_PINS.index(pin), f'Pin {pin}')
        elif pin == '16':
            text_entry('R', y, T['alt'], 'wo', 610, 'm small')
        else:
            o.append(f'<text x="{BX1 + 10}" y="{y + 4}" class="m small">{T["free"]}</text>')

    ny = H - 40
    o.append(f'<text x="24" y="{ny}" class="m">{esc(T["note1"])}</text>')
    o.append(f'<text x="24" y="{ny + 20}" class="m">{esc(T["note2"])}</text>')
    o.append('</svg>')
    return '\n'.join(o) + '\n'


if __name__ == '__main__':
    docs = Path(__file__).resolve().parent.parent / 'docs'
    for lang in TEXT:
        (docs / f'wiring-{lang}.svg').write_text(build(lang), encoding='utf-8')
        print('wrote', docs / f'wiring-{lang}.svg')
