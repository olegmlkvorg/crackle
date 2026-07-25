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
    # The machine start block (START_PRINT + Creality's own prime) legitimately lifts to Z3 and
    # comes back down to Z0.2, and homes inside a macro rather than a literal G28. Checking the
    # body only — a validator that cries wolf on correct machine gcode trains you to ignore it.
    body = False
    # Generators that move Z DURING extrusion declare it. For them, dipping below the nominal layer
    # height is the intended 'press' half of the cycle, not ploughing — so the relative check is
    # replaced by an ABSOLUTE plate floor, which is the thing that actually breaks hardware.
    z_modulated = '; Z_MODULATED' in open(path).read()
    Z_PLATE_FLOOR = 0.12
    z = 0.0; e = 0.0; x = y = 0.0; layer_floor = 0.0
    abs_e = True
    problems, warns = [], []
    travel_mm = extrude_mm = 0.0
    feed = 1200.0; secs = 0.0
    zs, temps, maxz = [], [], 0.0
    n = 0
    for ln, raw in enumerate(open(path), 1):
        # Body-mode markers. MUST cover every generator, because a file whose marker is missing
        # gets ZERO body checks and still prints a green tick — silence is not success.
        # Every generator emits '; BODY_START' immediately before its geometry. Keying on one
        # standard marker means a NEW generator cannot silently escape checking — the older
        # per-tool markers are kept only so existing files still validate.
        if ('; BODY_START' in raw
                or 'base layer 1' in raw or 'web layer 1 ' in raw
                or raw.startswith('; layer 1 ') or '; ramp starts' in raw
                or '---- band 1' in raw): body = True
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
            mf = re.search(r'F([\d.]+)', s)
            if mf: feed = float(mf.group(1))
            d = math.dist((x, y), (nx, ny))
            secs += d / max(feed/60.0, 1e-6)          # use the ACTUAL commanded feedrate
            if me:
                ev = float(me.group(1))
                de = ev - e if abs_e else ev
                if body and abs_e and de < -1e-6:
                    problems.append(f"L{ln}: absolute E goes BACKWARDS ({e:.3f}->{ev:.3f}) — that is an unintended retraction")
                e = ev if abs_e else e + ev
                extrude_mm += d
            else:
                travel_mm += d
            if body and nz < z - 1e-6 and nz < maxz - 1e-6:
                # A WEAVE lifts over an existing bead and comes back down to the same layer Z.
                # That descent is the whole point, so it is only ploughing if it goes BELOW the
                # layer height it started from.
                if z_modulated:
                    if nz < Z_PLATE_FLOOR:
                        problems.append(f"L{ln}: Z {nz} is below the {Z_PLATE_FLOOR}mm plate floor "
                                        f"— nozzle would scrape the bed")
                elif nz < layer_floor - 1e-6:
                    problems.append(f"L{ln}: Z descends to {nz} below layer floor {layer_floor} "
                                    f"— nozzle would plough the part")
            if not (0 <= nx <= BED[0] and 0 <= ny <= BED[1]):
                problems.append(f"L{ln}: XY off bed ({nx},{ny})")
            x, y, z = nx, ny, nz; maxz = max(maxz, z); zs.append(z)
            if 'Z' in s and 'E' not in s:      # a bare Z move sets the layer floor
                layer_floor = nz
    if not body:
        # The single most dangerous outcome: a file that silently receives no checks and passes.
        problems.append("BODY NEVER STARTED — no recognised layer marker, so the Z-plough, "
                        "backwards-extrusion and off-bed checks NEVER RAN. This file is unchecked, "
                        "not clean. Add its marker to validate.py.")
    if not any(t >= 150 for t in temps): problems.append("no hotend temp >=150 commanded")
    src = open(path).read()
    if 'G28' not in src and 'START_PRINT' not in src:
        # A deliberate no-home file is a real tier (back-to-back iteration on an already-homed
        # machine). Klipper refuses to move an unhomed axis, so this fails SAFELY rather than
        # crashing — it is a warning, not a defect. Unmarked missing-home is still a failure.
        if 'NO HOME' in src:
            warns.append("no homing — deliberate. Machine must still be homed from a previous run.")
        else:
            problems.append("never homes (no G28 and no START_PRINT macro)")
    ratio = travel_mm / max(extrude_mm, 1e-9)
    # v2: strands are DRAWN (G1 at travel feedrate with a small E), so travel:extrude no longer
    # measures web content. Count fast extrusion moves instead — those are the strands.
    if 'crackle' in path:
        strands = len(re.findall(r'^G1 F(?:[6-9]\d{3}|\d{5,}) .*E', src, re.M))
        print(f"  strand moves (fast G1 w/ E): {strands}")
        if strands < 50: warns.append(f"only {strands} strand moves — the web may be sparse")
    mins = secs / 60.0        # from the real F values (ignores accel, so it's a lower bound)
    print(f"\n{path}")
    print(f"  lines={n}  maxZ={maxz:.2f}mm  travel={travel_mm/1000:.1f}m  extrude={extrude_mm/1000:.1f}m"
          f"  travel:extrude={ratio:.1f}:1")
    print(f"  est. time ~{mins:.1f} min (motion only, no accel/heat)")
    for w in warns: print("  WARN ", w)
    for p in problems: print("  FAIL ", p)
    if not problems: print("  ✅ passes")
    return not problems, mins

if __name__ == "__main__":
    ok_all = True
    for f in sys.argv[1:]:
        ok, _ = check(f); ok_all &= ok
    sys.exit(0 if ok_all else 1)
