"""Draufsicht des Geraets fuer den Mapper (docs/index.html, Block zwischen den DEVICE-Markern).

Projiziert die Druckteile in Montagelage von oben (Umrisse als SVG-Pfade, Modell-mm) und berechnet die Lage der
Tastenkappen wie main.scad (key_mat). Quelle ist das OpenSCAD-Projekt; Pfad als Argument oder Standard.
Run: python tools/make_outline.py [Pfad zum jasp-keypad-Projekt]
"""
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

PROJ = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\MBran\openscad-projects\jasp-keypad")
SRC, OUT = PROJ / "src", PROJ / "output"
HTML = Path(__file__).resolve().parent.parent / "docs" / "index.html"

scad = (SRC / "main.scad").read_text(encoding="utf-8")
placement = (SRC / "original" / "placement.scad").read_text(encoding="utf-8")


def num(name):
    return eval(re.search(rf"^{name}\s*=\s*([^;]+);", scad, re.M).group(1).split("//")[0])


def mat(name):
    return np.array(eval(re.search(rf"^{name}\s*=\s*(.*?);", placement, re.M).group(1)))


def outline(mesh, tol=0.12, glatt=0.0):
    poly = trimesh.path.polygons.projected(mesh, normal=[0, 0, 1], ignore_sign=True)
    poly = unary_union(poly).buffer(0.05).buffer(-0.05)
    if glatt:   # Zacken abschneiden (oeffnen), Kerben fuellen (schliessen) - nur fuers Bild
        poly = poly.buffer(-glatt).buffer(glatt).buffer(glatt).buffer(-glatt)
    poly = poly.simplify(tol)
    polys = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
    d = []
    for p in polys:
        if p.area < 4:
            continue
        for ring in [p.exterior]:   # nur Aussenkontur: Loecher (Schalterausschnitte) braucht das Bild nicht
            pts = np.asarray(ring.coords)[:-1]
            d.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")
    return " ".join(d)


def load(path, matrix=None):
    m = trimesh.load(path)
    if matrix is not None:
        m.apply_transform(matrix)
    return m


# --- Teile in Montagelage ---
parts = {
    "wrist": load(SRC / "breit" / "wristrest.stl"),
    "body": load(OUT / "main-body-integrated.stl"),
    "palm": load(SRC / "breit" / "palmrest.stl"),
    "housing": load(OUT / "_daumentaste_aufnahme.stl"),
    "shell": load(OUT / "oberschale-integrated.stl"),
}
shapes = {k: outline(v, glatt=3.0 if k == "shell" else 0.0) for k, v in parts.items()}
allb = np.vstack([m.bounds for m in parts.values()])

# --- Tastenkappen (wie key_mat in main.scad) ---
c_, s_ = math.cos, math.sin


def T(v):
    M = np.eye(4); M[:3, 3] = v; return M


def Rx(a):
    a = math.radians(a); return np.array([[1, 0, 0, 0], [0, c_(a), -s_(a), 0], [0, s_(a), c_(a), 0], [0, 0, 0, 1]])


def Ry(a):
    a = math.radians(a); return np.array([[c_(a), 0, s_(a), 0], [0, 1, 0, 0], [-s_(a), 0, c_(a), 0], [0, 0, 0, 1]])


def Rz(a):
    a = math.radians(a); return np.array([[c_(a), -s_(a), 0, 0], [s_(a), c_(a), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])


cap_w, cap_d = num("cap_width"), num("cap_depth")
cap_h = num("v2_stiel_oben") + num("kappe_dicke")
rs = max(cap_d + num("reihen_luecke"), 16.5)
tent, tilt = num("neigung_zum_daumen"), num("neigung_zur_hand")
shift = num("tastenfeld_verschieben")
fingers = [num(n) for n in ["zeigefinger", "mittelfinger", "ringfinger", "kleiner_finger"]]
splay = num("finger_spreizung")
k_o, k_u = num("klappwinkel_oben"), num("klappwinkel_unten")


def key_mat(c, r):
    f = fingers[c]
    fold = (T([0, rs / 2, cap_h]) @ Rx(k_o) @ T([0, rs / 2, -cap_h]) if r == 2 else
            T([0, -rs / 2, cap_h]) @ Rx(-k_u) @ T([0, -rs / 2, -cap_h]) if r == 0 else np.eye(4))
    return (T([shift[0], shift[1], 0]) @ T([39, 0, 0]) @ Ry(-tent) @ T([-39, 0, 0])
            @ T([f[0], f[1], f[2] - cap_h]) @ Rz(splay[c]) @ Rx(tilt) @ fold)


keys = []
for slot in range(12):
    row, col = 2 - slot // 4, slot % 4          # Slot-Reihe 0 = oben = Modell-Reihe 2
    M = key_mat(col, row)
    quad = [(M @ [x, y, cap_h, 1])[:2] for x, y in
            [(-cap_w / 2, -cap_d / 2), (cap_w / 2, -cap_d / 2), (cap_w / 2, cap_d / 2), (-cap_w / 2, cap_d / 2)]]
    keys.append([[round(float(x), 2), round(float(y), 2)] for x, y in quad])

# Daumentaste (daumentaste.py): Mitte, Drehung, Kappe 16,5 x 17,5
dt = (SRC / "daumentaste.py").read_text(encoding="utf-8")
tm = eval(re.search(r"^taste_mitte = (\([^)]*\))", dt, re.M).group(1))
rot = math.degrees(math.atan2(-0.38211, 0.82194))
R = np.array([[c_(math.radians(rot)), -s_(math.radians(rot))], [s_(math.radians(rot)), c_(math.radians(rot))]])
keys.append([[round(float(p[0]), 2), round(float(p[1]), 2)] for p in
             (R @ np.array([[-8.25, -8.75], [8.25, -8.75], [8.25, 8.75], [-8.25, 8.75]]).T).T + tm])

# Stick-Kappe von oben: Scheibe d = 21 um die Stick-Achse, 27,2 mm vor dem Muldenboden
F = mat("placement_stick_frame")
axis, origin = F[:3, 2], F[:3, 3]
centre = origin + 27.2 * axis
u = np.cross(axis, [0, 0, 1.0]); u /= np.linalg.norm(u)
v = np.cross(axis, u)
disc = [centre + 10.5 * (math.cos(t) * u + math.sin(t) * v) for t in np.linspace(0, 2 * math.pi, 40, endpoint=False)]
stick = "M" + " L".join(f"{p[0]:.1f} {p[1]:.1f}" for p in disc) + " Z"

data = {
    "bounds": [round(float(allb[:, 0].min()), 1), round(float(allb[:, 1].min()), 1),
               round(float(allb[:, 0].max()), 1), round(float(allb[:, 1].max()), 1)],
    "parts": shapes, "keys": keys, "stick": stick,
    "stickCentre": [round(float(centre[0]), 1), round(float(centre[1]), 1)],
}
block = "const DEVICE = " + json.dumps(data, separators=(",", ":")) + ";"
html = HTML.read_text(encoding="utf-8")
new = re.sub(r"(// <DEVICE>\n).*?(\n// </DEVICE>)", lambda m: m.group(1) + block + m.group(2), html, flags=re.S)
assert new != html or block in html, "DEVICE-Marker fehlen in index.html"
HTML.write_text(new, encoding="utf-8")
print("Draufsicht geschrieben:", data["bounds"], f"{len(block) / 1024:.0f} KB")
