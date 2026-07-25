#!/usr/bin/env python3
"""Sanity-check hand-emitted gcode before it touches a printer.

Hand-written gcode has no slicer to catch you. These are the checks whose failure would either
waste a print or damage something: Z never descends into the part, absolute-E never goes backwards
(that's an un-commanded retraction), nothing leaves the bed, temps are sane, and the travel:extrude
ratio is actually high (if it isn't, we're not making a web).

Usage: python3 validate.py out/*.gcode
"""
import re, sys, math

BED = (350, 350)   # K2 Plus

def check(path):
    z = 0.0; e = 0.0; x = y = 0.0
    abs_e = True
    problems, warns = [], []
    travel_mm = extrude_mm = 0.0
    zs, temps, maxz = [], [], 0.0
    n = 0
    for ln, raw in enumerate(open(path), 1):
        s = raw.split(';')[0].strip()
        if not s: continue
        n += 1
        if s.startswith('M82'): abs_e = True
        elif s.startswith('M83'): abs_e = False
        elif s.startswith('G92'):
            m = re.search(r'E([-\d.]+)', s)
            if m: e = float(m.group(1))
        elif s.startswith(('M104', 'M109')):
            m = re.search(r'S(\d+)', s); temps.append(int(m.group(1))) if m else None
        elif s.startswith(('G0', 'G1')):
            nx = float(re.search(r'X([-\d.]+)', s).group(1)) if 'X' in s else x
            ny = float(re.search(r'Y([-\d.]+)', s).group(1)) if 'Y' in s else y
            nz = float(re.search(r'Z([-\d.]+)', s).group(1)) if 'Z' in s else z
            me = re.search(r'E([-\d.]+)', s)
            d = math.dist((x, y), (nx, ny))
            if me:
                ev = float(me.group(1))
                de = ev - e if abs_e else ev
                if abs_e and de < -1e-6:
                    problems.append(f"L{ln}: absolute E goes BACKWARDS ({e:.3f}->{ev:.3f}) — that is an unintended retraction")
                e = ev if abs_e else e + ev
                extrude_mm += d
            else:
                travel_mm += d
            if nz < z - 1e-6 and nz < maxz - 1e-6:
                problems.append(f"L{ln}: Z descends to {nz} (below max {maxz}) — nozzle would plough the part")
            if not (0 <= nx <= BED[0] and 0 <= ny <= BED[1]):
                problems.append(f"L{ln}: XY off bed ({nx},{ny})")
            x, y, z = nx, ny, nz; maxz = max(maxz, z); zs.append(z)
    if not any(t >= 150 for t in temps): problems.append("no hotend temp >=150 commanded")
    if 'G28' not in open(path).read(): problems.append("never homes (G28)")
    ratio = travel_mm / max(extrude_mm, 1e-9)
    if ratio < 1.0: warns.append(f"travel:extrude = {ratio:.2f} — LOW; this may not build much web")
    # crude time estimate: travels at F6000, extrudes at F1200
    mins = travel_mm / 6000 + extrude_mm / 1200
    print(f"\n{path}")
    print(f"  lines={n}  maxZ={maxz:.2f}mm  travel={travel_mm/1000:.1f}m  extrude={extrude_mm/1000:.1f}m"
          f"  travel:extrude={ratio:.1f}:1")
    print(f"  est. time ~{mins:.1f} min   (PRD budget: <6 min)")
    for w in warns: print("  WARN ", w)
    for p in problems: print("  FAIL ", p)
    if not problems: print("  ✅ passes")
    return not problems, mins

if __name__ == "__main__":
    ok_all = True
    for f in sys.argv[1:]:
        ok, _ = check(f); ok_all &= ok
    sys.exit(0 if ok_all else 1)
