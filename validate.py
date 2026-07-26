#!/usr/bin/env python3
"""Sanity-check hand-emitted gcode before it touches a printer.

Hand-written gcode has no slicer to catch you. These are the checks whose failure would either
waste a print or damage something: Z never descends into the part, absolute-E never goes backwards
(that's an un-commanded retraction), nothing leaves the bed, temps are sane, and the travel:extrude
ratio is actually high (if it isn't, we're not making a web).

Usage: python3 validate.py out/*.gcode
"""
import re, sys, math, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

# THE PLATE IS PER MACHINE and must come from the file, not from a constant. This was hardcoded to
# the K2's 350x350 while five of the seven generators DEFAULT to the K1C's 220x220 — so the widest
# machine's plate was used to bounds-check files built for the narrowest, and an off-plate K1C file
# passed clean and was auto-started. machine.BED has held the real plates all along.
DEFAULT_BED = (350, 350)


def bed_for(path):
    """Plate size from the file's own `; PRINTER=` stamp."""
    for ln in open(path):
        if ln.startswith('; PRINTER='):
            return machine.BED.get(ln.split('=', 1)[1].strip(), DEFAULT_BED)
        if 'BODY_START' in ln:
            break
    return None

FIL_AREA = math.pi * (1.75 / 2) ** 2


def check(path):
    BED = bed_for(path) or DEFAULT_BED
    _unstamped = bed_for(path) is None
    # The machine start block (START_PRINT + Creality's own prime) legitimately lifts to Z3 and
    # comes back down to Z0.2, and homes inside a macro rather than a literal G28. Checking the
    # body only — a validator that cries wolf on correct machine gcode trains you to ignore it.
    body = False
    # Generators that move Z DURING extrusion declare it. For them, dipping below the nominal layer
    # height is the intended 'press' half of the cycle, not ploughing — so the relative check is
    # replaced by an ABSOLUTE plate floor, which is the thing that actually breaks hardware.
    z_modulated = '; Z_MODULATED' in open(path).read()
    _sequential_file = '; SEQUENTIAL=' in open(path).read()
    # Plate floor lowered to match machine.PRESS_HARD (0.10), which is now the project's deliberate
    # method rather than an accident — everything anchoring to the plate is crushed into it, because
    # this work hangs things in the air and every thrown arc pulls UPWARD on its foot.
    # 0.06 remains a real floor: below that a 0.8 nozzle is not squashing plastic, it is dragging on
    # the sheet. The check still catches genuine mistakes; it no longer refuses the technique.
    Z_PLATE_FLOOR = 0.06
    z = 0.0; e = 0.0; x = y = 0.0; layer_floor = 0.0
    abs_e = True
    problems, warns = [], []
    travel_mm = extrude_mm = 0.0
    feed = 1200.0; secs = 0.0
    zs, temps, maxz = [], [], 0.0
    _seq_ceiling = 0.0   # highest Z the head has reached since the last descent
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
                elif nz < layer_floor - 1e-6 and not _sequential_file:
                    problems.append(f"L{ln}: Z descends to {nz} below layer floor {layer_floor} "
                                    f"— nozzle would plough the part")
                elif nz < layer_floor - 1e-6:
                    # A sequential plate legitimately returns to layer 1 when it starts the NEXT
                    # part. That is only safe if the head cleared the finished parts first, so the
                    # descent must be preceded by a lift to at least the finished height.
                    if _seq_ceiling < layer_floor - 1e-6:
                        problems.append(
                            f"L{ln}: Z drops to {nz} for a new part but the head only reached "
                            f"{_seq_ceiling} — it never cleared the {layer_floor}mm parts already "
                            f"standing, so it would shear them off")
            if not (0 <= nx <= BED[0] and 0 <= ny <= BED[1]):
                problems.append(f"L{ln}: XY off bed ({nx},{ny})")
            _seq_ceiling = max(_seq_ceiling, nz) if nz >= z else 0.0
            x, y, z = nx, ny, nz; maxz = max(maxz, z); zs.append(z)
            if 'Z' in s and 'E' not in s and '; HOP' not in raw:
                # A HOP's lift is temporary and drops straight back — treating it as a new layer
                # floor makes the matching drop look like a plough. Layer changes set the floor;
                # hops do not.
                layer_floor = nz
    if not body:
        # The single most dangerous outcome: a file that silently receives no checks and passes.
        problems.append("BODY NEVER STARTED — no recognised layer marker, so the Z-plough, "
                        "backwards-extrusion and off-bed checks NEVER RAN. This file is unchecked, "
                        "not clean. Add its marker to validate.py.")
    # NO TRAVEL IS A RULE (machine.py). Zero non-extruding moves between the first extrusion and
    # the last. Two G0 are permitted and only two: reaching the prime start before any plastic
    # exists, and parking after the object is complete.
    _lines = open(path).read().split('\n')
    _seq = any(l.startswith('; SEQUENTIAL=') for l in _lines)
    _ext = [i for i, l in enumerate(_lines) if re.match(r'G1 .*E[\d.]', l)]
    if _ext:
        _inside = [i for i, l in enumerate(_lines)
                   if l.startswith('G0 ') and _ext[0] < i < _ext[-1]
                   and '; HOP' not in l and '; PRIME-TRAVEL' not in l]
        _hops = sum(1 for l in _lines if '; HOP over' in l)
        if _hops:
            print(f"  {_hops} inter-object hops (lifted, flow suspended, no retract)")
        if _inside and not _seq:
            problems.append(f"{len(_inside)} TRAVEL move(s) inside the object (first at line "
                            f"{_inside[0]+1}) — prints must be one continuous extrusion")
        elif _inside:
            # SEQUENTIAL PLATES TRAVEL ON PURPOSE. Oleg, 2026-07-26: "max out the speed when travel
            # to next object and suspend the flow for a travel (dont retract)". The no-travel rule
            # was written for ONE continuous part, where a hop is a seam; between two parts 12mm
            # apart on open glass a thin link is a string that welds the plate together.
            #
            # So the rule is not dropped, it is REPLACED by stricter ones that a stamp cannot
            # excuse: a travel may not extrude, and it may not drag at layer height.
            _bad_e = [i for i in _inside if re.search(r'E[\d.]', _lines[i])]
            if _bad_e:
                problems.append(f"{len(_bad_e)} travel move(s) EXTRUDE (first at line "
                                f"{_bad_e[0]+1}) — a travel must suspend flow, not thin it")
            _far = [i for i in _inside
                    if not any(re.match(r'G0 Z[\d.]+', _lines[j]) for j in range(max(0, i-3), i))]
            _drag = [i for i in _far if re.search(r'X[-\d.]+ Y[-\d.]+', _lines[i])
                     and not re.search(r'Z', _lines[i])]
            print(f"  sequential: {len(_inside)} travels, {len(_bad_e)} extruding (must be 0)")
    # PARTS MUST NOT OVERLAP. This is the check that was missing when a sequential plate stacked
    # all 15 parts on the centre of the bed and the head drove into a finished part — audible, and
    # a printer shutdown. EVERY MOVE IN THAT FILE WAS INDIVIDUALLY VALID. The error existed only in
    # the relationship BETWEEN parts, which is exactly the class of bug a per-move validator misses,
    # so it has to be checked as geometry: two parts printed one after another may not share ground.
    if _seq:
        _bb = []          # (label, minx, maxx, miny, maxy)
        _cur, _xs, _ys = "part 1", [], []
        for l in _lines:
            if l.startswith('; ---- part'):
                if _xs:
                    _bb.append((_cur, min(_xs), max(_xs), min(_ys), max(_ys)))
                _cur = l.strip('; -').split(':')[0].strip(); _xs, _ys = [], []
            # A PART'S FOOTPRINT IS WHERE IT DEPOSITS MATERIAL, not everywhere the head went.
            # Including travels and the end-of-print park put Y340 inside the last part's box and
            # reported 15 phantom overlaps on a plate whose parts were provably disjoint. Measure
            # extruding moves only.
            _m = re.match(r'^G1 .*X([-\d.]+) Y([-\d.]+).*E[\d.]', l)
            if _m:
                _xs.append(float(_m.group(1))); _ys.append(float(_m.group(2)))
        if _xs:
            _bb.append((_cur, min(_xs), max(_xs), min(_ys), max(_ys)))
        _clash = []
        for _i in range(len(_bb)):
            for _j in range(_i + 1, len(_bb)):
                _a, _b = _bb[_i], _bb[_j]
                _ox = min(_a[2], _b[2]) - max(_a[1], _b[1])
                _oy = min(_a[4], _b[4]) - max(_a[3], _b[3])
                if _ox > 0.5 and _oy > 0.5:
                    _clash.append((_a[0], _b[0], _ox, _oy))
        if _clash:
            _f = _clash[0]
            problems.append(
                f"{len(_clash)} pair(s) of sequentially-printed parts OVERLAP on the plate — "
                f"e.g. '{_f[0]}' and '{_f[1]}' share {_f[2]:.0f}x{_f[3]:.0f}mm. The head would "
                f"print the second one into the first and crash.")
        else:
            print(f"  sequential: {len(_bb)} part footprints, none overlapping")

    # NO TRAVEL MAY CROSS THE PART AT LAYER HEIGHT.
    # A non-extruding move is only safe if it is ABOVE everything already printed. 161 moves at
    # 120 mm/s at the current layer Z swept the nozzle through the fresh layer and knocked every
    # model off a K1C plate. Height alone decides this, so it is checkable exactly: track the
    # highest Z at which material has been deposited, and fail any long travel at or below it.
    _z = 0.0
    _max_printed = 0.0
    _plough = []
    for _i, _l in enumerate(_lines):
        # Reset at a part boundary: the head lifts clear between parts, and the NEW part's ground
        # is empty, so the previous part's height says nothing about what is under the nozzle now.
        # Without this the legitimate descent to start part 2 looks like a plough.
        if _l.startswith('; ---- part'):
            _max_printed = 0.0
        _mz = re.search(r'Z([\d.]+)', _l)
        if _l.startswith(('G0 ', 'G1 ')) and _mz:
            _z = float(_mz.group(1))
        if re.match(r'^G1 .*E[\d.]', _l):
            _max_printed = max(_max_printed, _z)
        elif _l.startswith('G0 ') and re.search(r'X[-\d.]+', _l) and re.search(r'Y[-\d.]+', _l):
            _mf = re.search(r'F(\d+)', _l)
            if _max_printed > 0.3 and _z <= _max_printed + 1e-6 and (not _mf or int(_mf.group(1)) > 3000):
                _plough.append((_i + 1, _z, _max_printed))
    if _plough:
        _p0 = _plough[0]
        problems.append(
            f"{len(_plough)} travel move(s) run AT OR BELOW the height of already-printed material "
            f"— e.g. line {_p0[0]} travels at Z{_p0[1]} with material standing at Z{_p0[2]}. The "
            f"nozzle would plough through the part. Lift clear before travelling. "
            f"(A travel AT the layer height is the damaging case, not merely below it — the "
            f"nozzle is exactly at the top of the material it just laid.)")

    # Z DESCENT WHILE EXTRUDING — the check that was silently dead.
    # The original test compared against `layer_floor`, which only updates on BARE Z moves; solid.py
    # carries Z on every extruding G1, so layer_floor never left its initial value and the check
    # could not fire. Verified by forcing it: a file climbing to Z5.1 and then extruding at Z1.5
    # passed clean. Track the highest Z at which material has actually been deposited instead.
    _pm = 0.0
    _pz = 0.0
    _dives = []
    for _i, _l in enumerate(_lines):
        if _l.startswith('; ---- part'):
            _pm = 0.0          # a new part stands on bare plate; the last part's height is irrelevant
        _b = _l.split(';')[0]
        _m = re.search(r'Z([\d.]+)', _b)
        if _b.startswith(('G0 ', 'G1 ')) and _m: _pz = float(_m.group(1))
        if re.match(r'^G1 .*E[\d.]', _b):
            if _pm > 0.3 and _pz < _pm - 0.35:
                _dives.append((_i + 1, _pz, _pm))
            _pm = max(_pm, _pz)
    if _dives:
        _d0 = _dives[0]
        problems.append(
            f"{len(_dives)} EXTRUDING move(s) below already-printed material — e.g. line {_d0[0]} "
            f"extrudes at Z{_d0[1]} with material standing at Z{_d0[2]}. The nozzle is inside the "
            f"part it already made.")

    # PER-MOVE STARVATION — classify by physics, not by opcode.
    # The existing starved-move check is an AGGREGATE (>5% of moves), which suppressed 244 genuinely
    # starved moves out of 62,965 because they were a small fraction. A single 18mm move dragged
    # across a part at 4% of the metered rate is a defect on its own, however rare it is: it is a
    # thread laid over open bores and over material, and it is exactly how the prime-handoff bug
    # stayed invisible. So this one fires on ANY single move.
    _fa = math.pi * (1.75 / 2) ** 2
    _z2 = 0.0; _px2 = _py2 = None; _pe2 = 0.0; _starved = []
    _nominal = None
    for _i, _l in enumerate(_lines):
        _b = _l.split(';')[0].strip()
        if not _b.startswith(('G0', 'G1')): continue
        _mx = re.search(r'X([-\d.]+)', _b); _my = re.search(r'Y([-\d.]+)', _b)
        _me = re.search(r'E([\d.]+)', _b)
        # A G0 MOVES THE HEAD TOO. Tracking position only from G1 measured every post-hop move from
        # the stale pre-hop position and invented a 146.8mm "starved" move that does not exist —
        # the third guard today whose first version measured the wrong quantity.
        if not _me:
            if _mx: _px2 = float(_mx.group(1))
            if _my: _py2 = float(_my.group(1))
            continue
        _nx = float(_mx.group(1)) if _mx else _px2
        _ny = float(_my.group(1)) if _my else _py2
        _ne = float(_me.group(1))
        if _px2 is not None and _nx is not None and _ne > _pe2:
            _d = math.dist((_px2, _py2), (_nx, _ny))
            if _d > 0.05:
                _x = (_ne - _pe2) * _fa / _d
                if _nominal is None or _x > _nominal: _nominal = _x
                if _nominal and _x < 0.25 * _nominal and _d > 2.0:
                    _starved.append((_i + 1, _d, _x, _nominal))
        if _nx is not None: _px2, _py2 = _nx, _ny
        _pe2 = max(_pe2, _ne)
    # thin inter-tile links are deliberate (hilbert --tile) and are stamped; everything else is not
    # Deliberate thin links are TAGGED in the source that emits them; anything untagged that is
    # starved is a bug. Tagging beats loosening the threshold — a looser threshold would have let
    # the 18mm prime thread through, which is the exact defect this guard exists to catch.
    _starved = [t for t in _starved if '; LINK' not in _lines[t[0] - 1]]
    if _starved:
        _w = max(_starved, key=lambda t: t[1])
        problems.append(
            f"{len(_starved)} STARVED move(s): extruding moves longer than 2mm laid at under a "
            f"quarter of the file's own bead. Worst: line {_w[0]}, {_w[1]:.1f}mm at "
            f"{_w[2]:.3f}mm2 against a {_w[3]:.3f}mm2 bead — that is a thread dragged across the "
            f"plate, not a printed line.")

    # OVERHANG — does each layer have anything to sit on?
    # No check in this toolchain ever asked. A belt shipped with 72.9% of its points extruded onto
    # nothing, because TPU tolerates it and every layer was individually valid; the defect existed
    # only BETWEEN consecutive layers. Sampled, because the exact computation is O(n*m) per pair
    # and these files run to a quarter-million lines.
    _ly = {}
    _zz = 0.0
    for _l in _lines:
        _b = _l.split(';')[0]
        _m = re.search(r'Z([\d.]+)', _b)
        if _b.startswith(('G0 ', 'G1 ')) and _m: _zz = round(float(_m.group(1)), 3)
        _mm = re.match(r'^G1 .*X([-\d.]+) Y([-\d.]+).*E[\d.]', _b)
        if _mm: _ly.setdefault(_zz, []).append((float(_mm.group(1)), float(_mm.group(2))))
    _zs = sorted(_ly)
    if len(_zs) > 2:
        _bead = 1.2
        _mb = re.search(r'bead ([\d.]+)x', open(path).read()[:4000])
        if _mb: _bead = float(_mb.group(1))
        _worstz, _worstf = None, 0.0
        for _a, _bz in zip(_zs, _zs[1:]):
            _A = _ly[_a]
            _B = _ly[_bz][::max(1, len(_ly[_bz]) // 400)]
            if len(_A) < 3 or len(_B) < 3: continue
            # INDEX THE LOWER LAYER IN FULL. Sampling it to 250 points spread over a 315mm plate
            # put the nearest sample far from every query point and reported 94% of a perfectly
            # supported layer as overhanging — the same measure-the-easy-quantity error this guard
            # exists to catch. A spatial hash at bead resolution is exact enough and O(n).
            _cell = _bead
            _grid = set()
            for _q in _A:
                _grid.add((int(_q[0] // _cell), int(_q[1] // _cell)))
            def _supported(_p):
                _cx, _cy = int(_p[0] // _cell), int(_p[1] // _cell)
                return any((_cx + _dx, _cy + _dy) in _grid
                           for _dx in (-1, 0, 1) for _dy in (-1, 0, 1))
            _un = sum(1 for _p in _B if not _supported(_p))
            _frac = _un / len(_B)
            if _frac > _worstf: _worstf, _worstz = _frac, (_a, _bz)
        if _worstf > 0.05:
            problems.append(
                f"OVERHANG: {_worstf*100:.0f}% of layer Z{_worstz[1]} has no material within one "
                f"bead ({_bead}mm) of it on layer Z{_worstz[0]} — that fraction of the layer is "
                f"being extruded onto nothing. Ramp the change over more layers.")

    # STARVED MOVES. Feedrates PERSIST in gcode, so a slow press or a stationary dab leaves every
    # following move crawling until something sets F again — long stretches ran at 24 mm3/s against
    # a 55 target and looked like the extruder had paused. Nothing was paused; it was starved.
    # Oleg spotted it by eye on the plate (2026-07-25); nothing in this file would have.
    import math as _m
    _area = _m.pi * (1.75 / 2) ** 2
    _px = _py = _pz = None; _pe = None; _cf = None; _starved = 0; _moves = 0; _first = None
    # lowest Z at which anything is extruded = the first layer
    _minz = min([float(_q.group(1)) for _q in
                 (re.search(r'Z([\d.]+)', _l) for _l in _lines
                  if re.match(r'^G1 .*E[\d.]', _l) and 'Z' in _l) if _q] or [0.0])
    _target = None
    for _ln in open(path):
        _t = _ln.split(';')[0].strip()
        if _ln.startswith('; flow=') or 'mm3/s' in _ln:
            _mm = re.search(r'flow=([\d.]+)', _ln)
            if _mm and _target is None: _target = float(_mm.group(1))
        if not _t.startswith(('G0', 'G1')):
            if _t.startswith('G92'):
                _m2 = re.search(r'E([-\d.]+)', _t)
                if _m2: _pe = float(_m2.group(1))
            continue
        _mf = re.search(r'F(\d+)', _t)
        if _mf: _cf = int(_mf.group(1))
        _mx = re.search(r'X([-\d.]+)', _t); _my = re.search(r'Y([-\d.]+)', _t)
        _mz = re.search(r'Z([-\d.]+)', _t); _me = re.search(r'E([\d.]+)', _t)
        _nx = float(_mx.group(1)) if _mx else _px
        _ny = float(_my.group(1)) if _my else _py
        _nz = float(_mz.group(1)) if _mz else _pz
        if None not in (_px, _py, _pz, _nx, _ny, _nz) and _t.startswith('G1') and _target:
            _d = _m.dist((_px, _py, _pz), (_nx, _ny, _nz))
            # THE FIRST LAYER IS METERED DIFFERENTLY ON PURPOSE, in every generator: it is
            # pressed thinner than the body, so its flow is legitimately a fraction of the target.
            # This check counted it as starvation and only passed on tall parts by luck — on a
            # 23-layer plate layer 1 is 4% of moves, just under the 5% threshold; on a 3-layer tray
            # it is 33% and the file was rejected. Exclude it explicitly instead of relying on the
            # part being tall enough to dilute it.
            if _d > 1e-6 and _me and _pe is not None and float(_me.group(1)) > _pe and _cf \
                    and _nz > _minz + 1e-6:
                _moves += 1
                _q = (float(_me.group(1)) - _pe) * _area / _d * (_cf / 60)
                if _q < _target * 0.5:
                    _starved += 1
        if _me: _pe = float(_me.group(1))
        _px, _py, _pz = _nx, _ny, _nz
    if _target and _moves and _starved > _moves * 0.05:
        problems.append(f"{_starved} of {_moves} moves run below HALF the {_target} mm3/s target — "
                        f"a slow move probably left its feedrate set (F persists in gcode)")
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
    # CONTENT CHECK — by cross-section, not by feedrate.
    # The old version matched a regex on F-values (F6000-F9999 or 5+ digits) to identify strands.
    # That is decoupled from anything physical: at --max-flow 22, the flow this project actually
    # measured, travel_f lands at ~5610 and the regex reported ZERO strands on a file containing
    # 239 — a false alarm on a correct file, which teaches you to ignore the warning. At higher
    # flows it matched the pillar moves too and reported 6x the truth. Found by the adversarial
    # audit, 2026-07-25.
    # Cross-section = (filament consumed / distance travelled) * filament area, which is the
    # width*height of the bead being laid. Strands and pillar lines differ in it by construction,
    # so it separates them regardless of how fast either is moving.
    xs_hist = {}
    px = py = None; pe = None; abs2 = True
    for raw in open(path):
        t = raw.split(';')[0].strip()
        if t.startswith('M83'): abs2 = False
        elif t.startswith('M82'): abs2 = True
        elif t.startswith('G92'):
            m = re.search(r'E([-\d.]+)', t)
            if m: pe = float(m.group(1))
        elif t.startswith(('G0', 'G1')):
            nx = float(re.search(r'X([-\d.]+)', t).group(1)) if 'X' in t else px
            ny = float(re.search(r'Y([-\d.]+)', t).group(1)) if 'Y' in t else py
            me = re.search(r'E([-\d.]+)', t)
            if me and px is not None and nx is not None:
                ev = float(me.group(1))
                de = (ev - pe) if (abs2 and pe is not None) else ev
                d = math.dist((px, py), (nx, ny))
                if d > 1e-6 and de > 0:
                    xsec = de * (math.pi * (1.75 / 2) ** 2) / d
                    xs_hist[round(xsec, 2)] = xs_hist.get(round(xsec, 2), 0) + 1
                pe = ev if abs2 else (pe or 0) + ev
            px, py = nx, ny
    if xs_hist:
        top = sorted(xs_hist.items(), key=lambda kv: -kv[1])[:3]
        print("  bead cross-sections (mm2 -> moves): " +
              ", ".join(f"{k:.2f}->{v}" for k, v in top))
        if len(top) == 1 and 'crackle' in path:
            warns.append("only one bead cross-section — strands and pillars are indistinguishable, "
                         "so the web may not be forming")

    # EXTRUDER VELOCITY PER MOVE. A gcode file can be perfectly well-formed and still ask the
    # extruder for a speed no extruder can reach: on 2026-07-25 a stale position variable metered
    # 9.586mm of filament into a 0.98mm move, which is 224 mm/s of filament and 539 mm3/s of flow.
    # Klipper does not reject it -- the nozzle MCU shut down mid-print with "Stepper too far in
    # past". Flow is what this whole project is built on, so an emitted move that violates the cap
    # is a FAIL, not a warning.
    _cap = machine.FLOW * 1.35          # headroom for legitimate press/dab moves
    _f = 0.0
    _pp = None
    _pe = 0.0
    _worst = (0.0, 0)
    for _i, _ln in enumerate(open(path)):
        _m = re.match(r'G1 (?:F(\d+) )?(?:X([-\d.]+) Y([-\d.]+) )?(?:Z([\d.]+) )?E([-\d.]+)', _ln)
        if not _m:
            _mf = re.match(r'G1 F(\d+)\s*$', _ln)
            if _mf:
                _f = float(_mf.group(1)) / 60.0
            continue
        if _m.group(1):
            _f = float(_m.group(1)) / 60.0
        _e = float(_m.group(5)); _de = _e - _pe; _pe = _e
        if _m.group(2):
            _p = (float(_m.group(2)), float(_m.group(3)), float(_m.group(4) or 0))
            _d = math.dist(_p, _pp) if _pp else 0.0
            _pp = _p
        else:
            continue                     # stationary dab: no path, flow is dwell not rate
        if _d > 1e-6 and _de > 0 and _f > 0:
            _flow = _de * FIL_AREA * _f / _d
            if _flow > _worst[0]:
                _worst = (_flow, _i + 1)
    # ALSO CHECK AGAINST THE FLOW THE FILE ASKED FOR, not only the machine ceiling. A file can sit
    # far under machine.FLOW (55, a PLA number) while overshooting the flow its own header
    # requested — which is the number that actually matters for TPU. The header records it.
    _asked = None
    for _ln in open(path):
        _m = re.search(r'flow=([\d.]+)', _ln)
        if _m:
            _asked = float(_m.group(1))
            break
        if 'BODY_START' in _ln:
            break
    if _asked and _worst[0] > _asked * 1.05:
        problems.append(f"file asks for {_asked:.1f} mm3/s in its own header but a move at line "
                        f"{_worst[1]} implies {_worst[0]:.1f} — {100*(_worst[0]/_asked-1):.0f}% over "
                        f"what it claims to deliver.")
    elif _asked:
        print(f"  delivers the {_asked:.1f} mm3/s it asks for (peak {_worst[0]:.1f})")

    if _worst[0] > _cap:
        problems.append(f"move at line {_worst[1]} implies {_worst[0]:.0f} mm3/s "
                        f"(cap {machine.FLOW:.0f}) — the extruder cannot deliver this and the MCU "
                        f"will shut down; a position variable is probably stale")
    elif _worst[0]:
        print(f"  peak implied flow {_worst[0]:.1f} mm3/s (cap {machine.FLOW:.0f})")

    # HARD SPEED CAP — see machine.MAX_SPEED. A generator that derives speed from flow will happily
    # command 115 mm/s on a small part and throw it off the plate.
    #
    # The feedrate is STICKY in gcode: a bare "G1 F6900" line sets the speed for every move after
    # it. So the check must track the current F and test it at each MOVE, not only on lines that
    # happen to carry both F and E — my first version did the latter and passed a 115 mm/s file.
    # Only the BODY is checked. The prime/purge line runs fast on purpose (flowtest.py primes at
    # F7200) and is not part geometry — flagging it reported a 120 mm/s violation in a file whose
    # actual ramp tops out at 20. A guard that fires on the wrong thing is as useless as one that
    # does not fire.
    _f = 0.0
    _worst = (0.0, 0)
    _in_body = False
    for _i, _ln in enumerate(open(path)):
        if 'BODY_START' in _ln:
            _in_body = True
            _f = 0.0
            continue
        if not _in_body:
            continue
        _mf = re.search(r'\bF(\d+(?:\.\d+)?)', _ln)
        if _mf and _ln.startswith(('G1', 'G0')):
            _f = float(_mf.group(1)) / 60.0
        if _ln.startswith('G1') and ' E' in _ln and ('X' in _ln or 'Y' in _ln):
            if _f > _worst[0]:
                _worst = (_f, _i + 1)
    if _worst[0] > machine.MAX_SPEED + 0.5:
        problems.append(f"extruding move at line {_worst[1]} runs at {_worst[0]:.0f} mm/s — the hard "
                        f"cap is {machine.MAX_SPEED:.0f} (machine.MAX_SPEED). Lower --flow or widen "
                        f"the bead: speed = flow / (bead_w * layer_h).")
    else:
        print(f"  peak extruding speed {_worst[0]:.1f} mm/s (cap {machine.MAX_SPEED:.0f})")

    # MOVE RATE. Klipper stalls when the host cannot feed segments fast enough; the machine simply
    # FREEZES mid-print, with no error to read. A coupler shipped at 3354 moves/s because shapely
    # renders every circle at 96 segments regardless of radius, so small contours came out with
    # 0.009mm segments. machine.MAX_MOVES_PER_SEC is the measured threshold.
    _f = 0.0
    _pp = None
    _worst_rate = (0.0, 0)
    _body = False
    for _i, _ln in enumerate(open(path)):
        if 'BODY_START' in _ln:
            _body = True
            continue
        if not _body:
            continue
        _mf = re.search(r'\bF(\d+(?:\.\d+)?)', _ln)
        if _mf and _ln.startswith(('G1', 'G0')):
            _f = float(_mf.group(1)) / 60.0
        _m = re.match(r'G1 (?:F[\d.]+ )?X([-\d.]+) Y([-\d.]+)', _ln)
        if not _m:
            continue
        _p = (float(_m.group(1)), float(_m.group(2)))
        if _pp and _f > 0:
            _d = math.dist(_p, _pp)
            if _d > 1e-9:
                _r = _f / _d
                if _r > _worst_rate[0]:
                    _worst_rate = (_r, _i + 1)
        _pp = _p
    if _worst_rate[0] > machine.MAX_MOVES_PER_SEC:
        problems.append(f"line {_worst_rate[1]} needs {_worst_rate[0]:.0f} moves/s — the host stalls "
                        f"above ~{machine.MAX_MOVES_PER_SEC:.0f} and Klipper FREEZES with no error. "
                        f"Decimate points below ~0.3mm, or slow down.")
    elif _worst_rate[0]:
        print(f"  peak move rate {_worst_rate[0]:.0f}/s (stall ~{machine.MAX_MOVES_PER_SEC:.0f})")

    # TPU RUNS FULL FANS, ALWAYS. Oleg's rule, 2026-07-26, after finding the chamber fans at 0 on
    # a TPU print: "tpu must allway run full fans, add a guard". hilbert/honeycomb/waves never set
    # the aux fans at all, so every lattice printed with them off while belt/pulley/solid did set
    # them — an inconsistency no one would notice from the source.
    _mat = None
    for _ln in open(path):
        if _ln.startswith('; MATERIAL='):
            _mat = _ln.split('=', 1)[1].strip().lower()
        if 'BODY_START' in _ln:
            break
    if _mat == 'tpu':
        _head = ""
        for _ln in open(path):
            _head += _ln
            if 'BODY_START' in _ln:
                break
        _part = re.search(r'^M106 S(\d+)', _head, re.M)
        _aux = re.findall(r'SET_PIN PIN=fan\d VALUE=(\d+)', _head)
        _auxk = re.findall(r"SET_FAN_SPEED FAN=\w+ SPEED=([\d.]+)", _head)
        if not _part or int(_part.group(1)) < 250:
            problems.append(f"MATERIAL=tpu but the part fan is "
                            f"{_part.group(1) if _part else 'OFF (M107)'} — TPU runs full fans.")
        if _aux and min(int(v) for v in _aux) < 250:
            problems.append(f"MATERIAL=tpu but a chamber fan is at {min(int(v) for v in _aux)}/255 "
                            f"— TPU runs full fans.")
        if _auxk and min(float(v) for v in _auxk) < 0.98:
            problems.append(f"MATERIAL=tpu but a chamber fan is at {min(float(v) for v in _auxk)} "
                            f"— TPU runs full fans.")
        if not _aux and not _auxk:
            problems.append("MATERIAL=tpu but the file sets no chamber fans at all — "
                            "TPU runs full fans.")

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
