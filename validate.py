#!/usr/bin/env python3
"""Sanity-check hand-emitted gcode before it touches a printer.

Hand-written gcode has no slicer to catch you. These are the checks whose failure would either
waste a print or damage something: Z never descends into the part, absolute-E never goes backwards
(that's an un-commanded retraction), nothing leaves the bed, temps are sane, and the travel:extrude
ratio is actually high (if it isn't, we're not making a web).

Usage: python3 validate.py out/*.gcode
"""
import re, sys, math, os, collections
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
    # Parsed up front because several checks need it and one of them (OVERHANG) runs before the
    # Z-ladder block where it used to be read. A stamp read late is a stamp that is missing early.
    _mlh0 = re.search(r'^; LAYER_H=([\d.]+)', open(path).read()[:4000], re.M)
    _lh = float(_mlh0.group(1)) if _mlh0 else None
    # A MISSING STAMP IS A FAILURE. RULES.md already CLAIMED this, but it was only implemented for
    # '; FLOW='. An independent audit proved the claim false for the other two: delete '; LAYER_H='
    # and R2 dies silently (a 1.9mm Z jump -- 3x the layer height, a floating line -- passed);
    # delete '; MATERIAL=' and R6 dies silently. A guard that switches itself off when its input
    # goes missing is worse than no guard, because the green tick is indistinguishable.
    _stamp_missing = []
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
    # the last. The permitted G0s are named, never inferred: reaching the prime start before any
    # plastic exists, parking after the object is complete, an inter-object HOP, and the PRIME
    # break-off -- an angled un-extruded wipe that snaps the prime bead off IN THE CORRIDOR so it
    # does not ride along and land on layer 1 (Oleg, 2026-07-27: "make the first sstripe of
    # extrudement disconnected from main model ... this will make our prints cleaner"). It sits
    # between the prime and the part, which is why it falls inside this window at all.
    _lines = open(path).read().split('\n')
    _seq = any(l.startswith('; SEQUENTIAL=') for l in _lines)
    _ext = [i for i, l in enumerate(_lines) if re.match(r'G1 .*E[\d.]', l)]
    if _ext:
        _inside = [i for i, l in enumerate(_lines)
                   if l.startswith('G0 ') and _ext[0] < i < _ext[-1]
                   and '; HOP' not in l and '; PRIME-TRAVEL' not in l
                   and '; PRIME break-off' not in l]
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
    # ...and then it cried wolf on the flagship, which is how the hero file came to be PUBLISHED
    # while failing five checks. The fixed version tracked the highest Z at which material had been
    # deposited ANYWHERE, with no XY at all. That is right for stacked layers and completely wrong
    # for ARCH geometry, where Z varies WITHIN a layer by design: nucleon --weld 0.5 lifts over each
    # crossing and comes back down, so every later base-level move looked like a dive into the part.
    # Measured on nucleon_N6_weld0.5: this reported 1620 offending moves implying a 7mm plunge; the
    # same file checked per-XY-cell in EMISSION ORDER has 168 offending samples, worst 0.349mm.
    # An order of magnitude of over-report — and a guard that loud on the flagship is one nobody reads.
    #
    # Material is now tracked per XY CELL and strictly in time order: a move is a dive only if the
    # nozzle passes under material already laid in the cell it is actually crossing.
    _CELL = 0.6
    _topo = {}
    _pz = 0.0
    _px = _py = None
    _dives = []
    for _i, _l in enumerate(_lines):
        if _l.startswith('; ---- part'):
            _topo = {}         # a new part stands on bare plate; the last part's height is irrelevant
        _b = _l.split(';')[0]
        if not _b.startswith(('G0 ', 'G1 ')):
            continue
        _m = re.search(r'Z([\d.]+)', _b)
        _mx = re.search(r'X([-\d.]+)', _b)
        _my = re.search(r'Y([-\d.]+)', _b)
        _nz = float(_m.group(1)) if _m else _pz
        _nx = float(_mx.group(1)) if _mx else _px
        _ny = float(_my.group(1)) if _my else _py
        if _nx is None or _ny is None:
            _pz = _nz
            continue
        _ext = bool(re.match(r'^G1 .*E[\d.]', _b))
        if _px is not None:
            _n = min(64, max(1, int(math.hypot(_nx - _px, _ny - _py) / _CELL)))  # bounded
            _worst = None
            for _k in range(_n + 1):
                _t = _k / _n
                _cx = int((_px + (_nx - _px) * _t) / _CELL)
                _cy = int((_py + (_ny - _py) * _t) / _CELL)
                _cz = _pz + (_nz - _pz) * _t
                _prev = _topo.get((_cx, _cy))
                if _prev is not None and _prev > 0.3 and _prev - _cz > 0.35:
                    if _worst is None or _prev - _cz > _worst[2] - _worst[1]:
                        _worst = (_i + 1, round(_cz, 3), round(_prev, 3))
                if _ext and (_prev is None or _cz > _prev):
                    _topo[(_cx, _cy)] = _cz
            if _worst and _ext:
                _dives.append(_worst)
        _px, _py, _pz = _nx, _ny, _nz
    if _dives:
        _d0 = max(_dives, key=lambda d: d[2] - d[1])    # report the WORST, not merely the first
        problems.append(
            f"{len(_dives)} EXTRUDING move(s) below already-printed material — worst at line "
            f"{_d0[0]}, extruding at Z{_d0[1]} where material already stands at Z{_d0[2]} in that "
            f"same XY cell ({_d0[2]-_d0[1]:.2f}mm into the part it already made).")

    # PER-MOVE STARVATION — classify by physics, not by opcode.
    # The existing starved-move check is an AGGREGATE (>5% of moves), which suppressed 244 genuinely
    # starved moves out of 62,965 because they were a small fraction. A single 18mm move dragged
    # across a part at 4% of the metered rate is a defect on its own, however rare it is: it is a
    # thread laid over open bores and over material, and it is exactly how the prime-handoff bug
    # stayed invisible. So this one fires on ANY single move.
    _fa = math.pi * (1.75 / 2) ** 2
    _z2 = 0.0; _px2 = _py2 = None; _pe2 = 0.0; _starved = []
    _nominal = None
    # THE PRIME IS DELIBERATELY HEAVY AND MUST NOT SET THE YARDSTICK.
    # Taking the nominal bead from the running maximum let the prime line (metered several times the
    # body bead, on purpose) define it — so on a single-layer file every real move measured as
    # starved. Only body moves define what normal looks like.
    _inbody = False
    for _i, _l in enumerate(_lines):
        if '; BODY_START' in _l: _inbody = True
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
                if _inbody and (_nominal is None or _x > _nominal): _nominal = _x
                if _nominal and _x < 0.25 * _nominal and _d > 2.0:
                    _starved.append((_i + 1, _d, _x, _nominal))
        if _nx is not None: _px2, _py2 = _nx, _ny
        _pe2 = max(_pe2, _ne)
    # thin inter-tile links are deliberate (hilbert --tile) and are stamped; everything else is not
    # Deliberate thin links are TAGGED in the source that emits them; anything untagged that is
    # starved is a bug. Tagging beats loosening the threshold — a looser threshold would have let
    # the 18mm prime thread through, which is the exact defect this guard exists to catch.
    _starved = [t for t in _starved
                if '; LINK' not in _lines[t[0] - 1] and '; RETRACE' not in _lines[t[0] - 1]]
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
    # ARCH GEOMETRY CANNOT BE READ BY A LAYER-PAIR CHECK, and pretending otherwise is what taught
    # everyone to ignore this validator. Binning layers by Z assumes Z is piecewise constant. Where
    # the generator varies Z WITHIN a layer on purpose (nucleon's weld lift, the wave), the file has
    # thousands of distinct Z values, each holding a handful of points, and consecutive pseudo-layers
    # 4 MICRONS apart naturally fail to support one another: measured "100% of layer Z0.544
    # unsupported by layer Z0.540". Generators that do this now stamp `; ARCH_LIFT=`. Skipping is
    # stated out loud, never silent — an unrun check reported as a pass is the worse failure.
    _arch = re.search(r'^; ARCH_LIFT=([\d.]+)', open(path).read()[:4000], re.M)
    if _arch and float(_arch.group(1)) > 0:
        print(f"  overhang check SKIPPED — file declares ARCH_LIFT={_arch.group(1)}mm, so Z varies "
              f"within a layer by design and layer-pair support is not measurable this way. "
              f"The per-XY-cell dive check still applies and did run.")
        _zs = []
    else:
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
            # THE FIRST LAYER IS WIDER THAN A BEAD, AND THE CHECK MUST KNOW IT. Layer 1 is laid
            # into a PRESS_HARD gap carrying the body's full mm2, so it spreads to
            # bead_w*layer_h/PRESS_HARD -- ~13mm at 2.17x0.6. Measuring support against a 2.17mm
            # radius then reports a perfectly-covered layer 2 as 22% overhanging. A false positive
            # is how a guard gets switched off, so the support radius uses the LOWER layer's real
            # width when that lower layer is the pressed first one.
            _cell = _bead
            if _lh and abs(_a - machine.PRESS_HARD) < 1e-6:
                _cell = max(_bead, _bead * _lh / machine.PRESS_HARD)
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
    # THE CAP BELONGS TO THE FILE'S MATERIAL, not to a module constant. Checking a matte-PLA part
    # (65 maintained) against machine.FLOW (a 55 PLA number) reports a wrong cap in the pass line
    # and would refuse a legitimate file. The header already states the material; read it.
    _fmat = None
    for _l in open(path):
        if _l.startswith('; MATERIAL='):
            _fmat = _l.split('=', 1)[1].strip().lower()
            break
        if 'BODY_START' in _l:
            break
    _base = machine.SUSTAINED_FLOW_BY_MATERIAL.get(_fmat, machine.FLOW)
    _cap = _base * 1.35                 # headroom for legitimate press/dab moves
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
    # A FILE MAY DECLARE MORE THAN ONE FLOW. Layer 1 is deliberately a different bead at a different
    # speed — wide and thin, to bond — so its rate is not the body's. Taking only the FIRST flow= in
    # the header made the validator flag the first layer as a 9% overrun against the body's number.
    # The contract is: no move may exceed the highest rate the file declares for itself.
    _asked = None
    for _ln in open(path):
        if 'BODY_START' in _ln:
            break
        _m = re.search(r'flow=([\d.]+)', _ln)
        if _m:
            _v = float(_m.group(1))
            _asked = _v if _asked is None else max(_asked, _v)
    if _asked and _worst[0] > _asked * 1.05:
        problems.append(f"file asks for {_asked:.1f} mm3/s in its own header but a move at line "
                        f"{_worst[1]} implies {_worst[0]:.1f} — {100*(_worst[0]/_asked-1):.0f}% over "
                        f"what it claims to deliver.")
    elif _asked:
        print(f"  delivers the {_asked:.1f} mm3/s it asks for (peak {_worst[0]:.1f})")

    # A FLOW TEST IS ALLOWED TO EXCEED THE CAP — finding a ceiling from underneath is impossible.
    # The exemption is NARROW: only this one check, only for a file that DECLARES itself a
    # measurement with `; FLOW_TEST=1`, and it is announced rather than silent. Every other guard
    # still applies. A part carries no such stamp and is refused exactly as before.
    _flowtest = bool(re.search(r"^; FLOW_TEST=1", open(path).read()[:4000], re.M))
    if _worst[0] > _cap and _flowtest:
        print(f"  flow cap NOT enforced: file declares FLOW_TEST=1 and peaks at "
              f"{_worst[0]:.0f} mm3/s against a {_base:.0f} cap — this is a measurement.")
    elif _worst[0] > _cap:
        problems.append(f"move at line {_worst[1]} implies {_worst[0]:.0f} mm3/s "
                        f"(cap {_base:.0f} for {_fmat}) — the extruder cannot deliver this and the MCU "
                        f"will shut down; a position variable is probably stale")
    elif _worst[0]:
        print(f"  peak implied flow {_worst[0]:.1f} mm3/s (cap {_base:.0f} for {_fmat})")

    # ========================= OLEG'S STANDING RULES, ENFORCED HERE =========================
    # These are not suggestions the generators may interpret. Every one of them was stated as an
    # absolute, and every one of them was then broken by a generator that had its own idea --
    # because the rule lived in a constant, or a comment, or my memory, none of which fail.
    #
    # Oleg, 2026-07-27: "why you keep annoying me with same errors again and again. why you dont
    # have guards to enforce my requirements". He is right. A rule enforced by my attention is a
    # rule that costs HIM attention. It belongs on the artifact, where routing around it is
    # impossible, and it must be shown able to FAIL or it is decoration.
    #
    #   R1  first layer pressed to PRESS_HARD          "the nozel need to be 0,1 to board"
    #   R2  no Z step above one layer height           "play Z smartly we dont want floaring lines"
    #   R3  one constant head speed                    "50 is our north star for moving"
    #   R4  one constant flow, first layer included    "flow must be constant"
    #
    # The ONLY licensed exception is the prime line, which is laid off the part before printing
    # starts. It is identified by its own comment, not by being slow -- otherwise "slow" becomes
    # a way to opt out of R3.
    _rules_txt = open(path).read()
    _decl_flow = None
    _mf = re.search(r'^; FLOW=([\d.]+)', _rules_txt, re.M)
    if _mf:
        _decl_flow = float(_mf.group(1))
    _xr, _yr, _er, _fr, _zr = None, None, 0.0, None, 0.0
    _spd, _flw, _nlink = {}, [], 0
    _area = math.pi * (1.75 / 2) ** 2
    for _raw in _rules_txt.splitlines():
        _code = _raw.split(';')[0].strip()
        _isprime = 'PRIME' in _raw.upper()
        if not _code.startswith(('G0', 'G1')):
            continue
        _g = dict(re.findall(r'\b([XYEFZ])(-?\d+(?:\.\d+)?)', _code))
        if 'Z' in _g: _zr = float(_g['Z'])
        if 'F' in _g:
            _fr = float(_g['F'])
        # LINK MOVES ARE DECLARED, NOT ASSUMED. solid.py labels its contour-to-contour connectors
        # '; LINK thin' and deliberately meters them down: they cross ground the NEXT contour will
        # cover, so a full bead there lays a second bead at the same Z, doubles the height and the
        # nozzle drags through it on the next layer. That is a real reason, and the generator
        # states it in the file rather than relying on the checker to guess. They are exempt from
        # R4 but COUNTED and reported, so an exemption can never hide a growing problem.
        _islink = 'LINK' in _raw.upper()
        if _islink:
            _nlink += 1
        _l1decl = re.search(r'^; SPEED_LAYER1=([\d.]+)', _rules_txt, re.M)
        _isl1 = bool(_l1decl) and _fr is not None and abs(_fr/60.0 - float(_l1decl.group(1))) < 0.6
        _pdecl = re.search(r'^; PRESSED_LAYER1=([\d.]+)', _rules_txt, re.M)
        if _pdecl and abs(_zr - float(_pdecl.group(1))) < 1e-6:
            _isl1 = True
        if 'X' in _g and 'E' in _g and _xr is not None and _fr and not _isprime and not _islink \
                and not _isl1:
            _d = math.hypot(float(_g['X']) - _xr, float(_g['Y']) - _yr)
            _de = float(_g['E']) - _er
            if _d > 0.05 and _de > 0:
                _sp = round(_fr / 60.0, 1)
                _spd[_sp] = _spd.get(_sp, 0) + 1
                _flw.append((_de * _area) / (_d / (_fr / 60.0)))
        if 'E' in _g:
            _er = float(_g['E'])
        if 'X' in _g:
            _xr = float(_g['X'])
        if 'Y' in _g:
            _yr = float(_g['Y'])
    # R3 IS ABOUT CONSTANCY, NOT ABOUT THE NUMBER 50.
    # Oleg, correcting my first implementation: "speed is not fixed - 50 is north star default
    # unless overruled by other constraints." What must hold is ONE speed within a print, so
    # material per mm does not change where the geometry is already tightest. The VALUE is the
    # north star unless a real constraint (flow ceiling, fat bead, low-flow material) pushes it
    # lower -- that is the wide-bead crawl working as intended. Never higher than the north star.
    #
    # Failing on "not exactly 50" made the wide-bead trick impossible and made me report TPU as
    # unprintable when it simply runs at 21 mm/s.
    if _spd:
        _ovr = re.search(r'^; SPEED_OVERRIDE=([\d.]+)', _rules_txt, re.M)
        _ceil = float(_ovr.group(1)) if _ovr else machine.MAX_SPEED
        if _ovr:
            print(f"  speed ceiling raised to {_ceil:g} mm/s by an explicit '; SPEED_OVERRIDE=' "
                  f"stamp — the north star is {machine.MAX_SPEED:g}")
        _fast = {k: v for k, v in _spd.items() if k > _ceil + 0.6}
        if _fast:
            problems.append(f"R3 speed ceiling: {sum(_fast.values())} extruding moves exceed the "
                            f"{_ceil:g} mm/s ceiling (found {sorted(_fast)[:4]})")
        # A DECLARED FIRST-LAYER SPEED IS LEGITIMATE. Oleg, 2026-07-27: "lets also try first layer
        # normal speed and ret layers double speed". Layer 1 is already a different cross-section
        # (pressed to PRESS_HARD), so it is a different regime, not a wobble inside one. What R3
        # protects is constancy WITHIN the body. The file must declare it: '; SPEED_LAYER1='.
        _decl_l1 = re.search(r'^; SPEED_LAYER1=([\d.]+)', _rules_txt, re.M)
        if _decl_l1 and len(_spd) == 2:
            _l1v = round(float(_decl_l1.group(1)), 1)
            if _l1v in _spd:
                print(f"  layer 1 declared at {_l1v:g} mm/s, body at "
                      f"{[k for k in _spd if k != _l1v][0]:g} mm/s — two declared regimes")
                _spd = {k: v for k, v in _spd.items() if k != _l1v}
        if len(_spd) > 1:
            _main = max(_spd, key=_spd.get)
            _other = {k: v for k, v in _spd.items() if k != _main}
            problems.append(f"R3 constant speed: this print runs at {len(_spd)} different speeds "
                            f"— {_main:g} mm/s for {_spd[_main]} moves, plus {sorted(_other)} — "
                            f"a head that changes speed changes material per mm. One speed per "
                            f"print; its value may be below {machine.MAX_SPEED:g} if a constraint "
                            f"requires it, but it must not vary.")
        elif _spd:
            _only = next(iter(_spd))
            if _only < machine.MAX_SPEED - 0.6:
                print(f"  runs at {_only:g} mm/s, below the {machine.MAX_SPEED:g} north star "
                      f"— legitimate if a constraint requires it (fat bead / low-flow material)")

    if _flw and not _decl_flow:
        problems.append("R4 cannot be checked: file carries no '; FLOW=' stamp, so constant flow "
                        "is unverifiable. Regenerate with a current generator.")
    # R4b FILL RATIO — the property "constant flow" was only ever a proxy for.
    # Raw flow equality and even deposition are the same thing ONLY when paths do not overlap.
    # On a self-crossing curve they are not, and the difference destroyed a part:
    #   * layer 1 at a 0.1 press carried the body's 1.20 mm2/mm. A 0.1 gap can hold that only if
    #     paths sit ~12mm apart; rosetta strands sit ~2mm apart -> 6.75x over-fill.
    #   * the body over-filled 1.72x because 91 self-crossings per layer stack two beads each.
    # MEASURED ON THE PLATE by Oleg: five layers that should stand 2.50mm stood 4.80mm, and the
    # part sheared off after four layers when the nozzle reached its own deposit.
    # RAW FLOW EQUALITY PASSED THAT FILE. This is the check that refuses it.
    #
    # HOW FAR THIS IS ACTUALLY VALIDATED — read before trusting a number it prints:
    #   * LAYER 1 (pressed): trustworthy in direction and roughly in size. It reads 2.40x on the
    #     file that sheared off and 1.13x on the corrected one.
    #   * BODY LAYERS: NOT validated. The model reads 1.13x where Oleg's ruler measured 1.72x
    #     (five layers standing 4.80mm against a commanded 2.50mm). It under-predicts by ~1.5x,
    #     because a union-of-footprints model does not capture how much height a bead-on-bead
    #     crossing actually adds.
    #   * I briefly claimed this guard "predicted Oleg's measurement". It did not. Its 1.98x was
    #     LAYER 1 only, and his 1.92x was the whole part's height ratio -- two different
    #     quantities that happened to land close. That is the measuring-the-easy-quantity error,
    #     and it was published before being checked.
    # So: use it to catch gross over-fill, do NOT use its body number to size flow. Flow
    # corrections come from a ruler on a printed part until this model is calibrated against one.
    if _lh:
        _pl = collections.defaultdict(list)
        _qx = _qy = None; _qe = 0.0; _qz = 0.0; _qin = False
        for _r2 in _rules_txt.splitlines():
            if 'BODY_START' in _r2: _qin = True
            _c2 = _r2.split(';')[0].strip()
            if not _c2.startswith(('G0', 'G1')): continue
            _g2 = dict(re.findall(r'\b([XYEZ])(-?\d+(?:\.\d+)?)', _c2))
            if 'Z' in _g2: _qz = float(_g2['Z'])
            if _qin and 'X' in _g2 and 'E' in _g2 and _qx is not None:
                _d2 = math.hypot(float(_g2['X']) - _qx, float(_g2['Y']) - _qy)
                _de2 = float(_g2['E']) - _qe
                if _d2 > 0.05 and _de2 > 0:
                    _pl[round(_qz, 2)].append((float(_g2['X']), float(_g2['Y']), _de2))
            if 'E' in _g2: _qe = float(_g2['E'])
            if 'X' in _g2: _qx = float(_g2['X'])
            if 'Y' in _g2: _qy = float(_g2['Y'])
        _mbw = re.search(r'bead[ =]([\d.]+)', _rules_txt[:4000])
        _bw2 = float(_mbw.group(1)) if _mbw else 2.0
        _fa2 = math.pi * (1.75 / 2) ** 2
        _ratios = []
        for _zz, _rows in _pl.items():
            if len(_rows) < 20: continue
            _vol2 = sum(r[2] for r in _rows) * _fa2
            _h2 = machine.PRESS_HARD if abs(_zz - machine.PRESS_HARD) < 1e-6 else _lh
            # COVERAGE MUST USE THE WIDTH THE MATERIAL ACTUALLY LANDS AT, not the nominal bead.
            # A pressed layer spreads: mm2-per-mm divided by the gap. At 1.20mm2 into 0.1mm that
            # is 12mm wide, not 2mm. Dilating by the bead made a healthy nucleon read 25x, which
            # is how a false positive gets a guard switched off. Measuring the deposit's own
            # geometry instead.
            _len2 = 0.0; _prev = None
            for _rx, _ry, _ in _rows:
                if _prev: _len2 += math.hypot(_rx - _prev[0], _ry - _prev[1])
                _prev = (_rx, _ry)
            _mm2 = _vol2 / max(_len2, 1e-9)
            _spread = min(max(_mm2 / _h2, _bw2), 40.0)
            _cl2 = max(_spread / 3.0, 0.3); _grid2 = set()
            # int(), not round(): round(1.5)->2 dilated a 2.0mm bead into a 3.33mm footprint,
            # over-stating coverage by 1.67x and under-stating every body layer's fill ratio.
            _k2 = max(0, int(_spread / (2 * _cl2)))
            for _rx, _ry, _ in _rows:
                _gx2, _gy2 = int(_rx // _cl2), int(_ry // _cl2)
                for _dx2 in range(-_k2, _k2 + 1):
                    for _dy2 in range(-_k2, _k2 + 1): _grid2.add((_gx2 + _dx2, _gy2 + _dy2))
            _cov2 = len(_grid2) * _cl2 * _cl2
            _ratios.append((_zz, _vol2 / max(_cov2 * _h2, 1e-9)))
        _pressed_ok = bool(re.search(r'^; PRESSED_LAYER1=', _rules_txt, re.M))
        if _ratios:
            _wz, _wr = max(_ratios, key=lambda t: t[1])
            if _wr > 1.35 and not _pressed_ok:
                problems.append(f"R4b fill ratio {_wr:.2f}x at Z{_wz} — this layer deposits "
                                f"{_wr:.2f}x more than its own height can hold over the area it "
                                f"covers. The surplus builds height until the nozzle reaches its "
                                f"own deposit and shears the part off the plate. Overlapping "
                                f"paths need LESS flow than a bead model predicts, not the same.")
            else:
                _note = " — layer 1 over-extrudes ON PURPOSE (wide line, welds to plate)" \
                        if _pressed_ok and _wr > 1.35 else " — 1.00 is exact"
                print(f"  fill ratio {_wr:.2f}x (worst layer, Z{_wz}){_note}")

    if _nlink:
        print(f"  {_nlink} declared LINK move(s) exempt from R4 (contour connectors, metered thin)")
    if _flw and _decl_flow:
        _lo = [f for f in _flw if f < _decl_flow * 0.80]
        _hi = [f for f in _flw if f > _decl_flow * 1.20]
        if _lo:
            problems.append(f"R4 constant flow: {len(_lo)} extruding moves deliver under 80% of "
                            f"the declared {_decl_flow:g} mm3/s (worst {min(_lo):.1f}) — the first "
                            f"layer is the usual offender and it is NOT an exception")
        if _hi:
            problems.append(f"R4 constant flow: {len(_hi)} extruding moves exceed 120% of the "
                            f"declared {_decl_flow:g} mm3/s (worst {max(_hi):.1f})")

    # FIRST LAYER MUST BE PRESSED TO THE PLATE, AND NOTHING MAY FLOAT ABOVE IT.
    # Oleg's rule -- "the nozel need to be 0,1 to board. we need adhesion" -- lived only as the
    # constant machine.PRESS_HARD, which generators were free to ignore. nucleon.py did: it carried
    # its own first_squish=0.85*layer_h model and laid layer 1 at 0.51mm. He caught it on the plate
    # TWICE. A rule that depends on every author remembering it is not a rule, so it is checked
    # here, on the artifact, where no generator can route around it.
    # The second half is his follow-on: "play Z smartly we dont want floaring lines". Rebasing
    # layer 1 to 0.1 without rebasing the ladder left a 1.10mm step onto layer 2 -- extruding into
    # air over a 0.60mm bead. Any step bigger than one layer height is a floating line.
    # ONLY Z MOVES THAT ARE FOLLOWED BY EXTRUSION ARE LAYERS. The end-of-print park lift is a Z
    # move too, and on a short part it fell inside the scan window and was reported as a 30.7mm
    # "floating line" -- a false positive that would refuse every 4-layer part.
    _zs, _pend = [], None
    for _l in open(path):
        _c = _l.split(';')[0].strip()
        _m = re.match(r'G1 (?:F\d+ )?Z(\d+\.\d+)$', _c)
        if _m:
            _pend = float(_m.group(1))
        elif _pend is not None and _c.startswith('G1') and ' E' in _c and 'X' in _c:
            if not _zs or _pend != _zs[-1]:
                _zs.append(_pend)
            _pend = None
        if len(_zs) > 6:
            break
    if _zs:
        if abs(_zs[0] - machine.PRESS_HARD) > 1e-6:
            problems.append(f"first layer is at Z{_zs[0]:.3f} but must be pressed to "
                            f"{machine.PRESS_HARD:.2f} — adhesion comes from the press, and this "
                            f"generator is using its own first-layer model")
        _steps = [round(_zs[i + 1] - _zs[i], 4) for i in range(len(_zs) - 1)]
        _big = [g for g in _steps if _lh and g > _lh + 1e-6]
        if _big:
            problems.append(f"Z steps {_big} exceed one layer height ({_lh}) — those layers "
                            f"extrude into air (floating lines)")

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
    _ovr2 = re.search(r'^; SPEED_OVERRIDE=([\d.]+)', open(path).read(), re.M)
    _cap2 = float(_ovr2.group(1)) if _ovr2 else machine.MAX_SPEED
    if _worst[0] > _cap2 + 0.5:
        problems.append(f"extruding move at line {_worst[1]} runs at {_worst[0]:.0f} mm/s — the hard "
                        f"cap is {_cap2:.0f}. Lower --flow or widen "
                        f"the bead: speed = flow / (bead_w * layer_h).")
    else:
        print(f"  peak extruding speed {_worst[0]:.1f} mm/s (cap {_cap2:.0f})")

    # MOVE RATE. Klipper stalls when the host cannot feed segments fast enough; the machine simply
    # FREEZES mid-print, with no error to read. A coupler shipped at 3354 moves/s because shapely
    # renders every circle at 96 segments regardless of radius, so small contours came out with
    # 0.009mm segments. machine.MAX_MOVES_PER_SEC is the measured threshold.
    _f = 0.0
    _pp = None
    _worst_rate = (0.0, 0)
    _win = []
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
                # A SUSTAINED RATE, NOT A SINGLE SEGMENT. Klipper freezes because the host cannot
                # REFILL the lookahead buffer, which takes many short moves in a row — one short
                # segment is absorbed and harmless. Measuring per-segment flagged a helical mixer
                # 132 times for its 132 layer-start steps (one 0.174mm move each), which no machine
                # would ever notice. The window is the buffer's own scale.
                _win.append((_d, _f))
                if len(_win) > 24:
                    _win.pop(0)
                if len(_win) == 24:
                    _t = sum(d / f for d, f in _win)
                    _r = len(_win) / _t if _t > 0 else 0
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

    # R5  DRY TRAVEL IS THE ENEMY. Oleg: "travel dry is ok, but avoid it at all costs" and
    # "you dont want to travel without filament, find a path of continious extrusion". This is a
    # design principle, not a hard physical limit, so it FAILS only when travel exceeds extrusion
    # -- a path spending more distance in the air than laying material has stopped being a
    # continuous stroke and become a series of hops. Below that it reports the number so the
    # figure is visible on every run instead of being discovered later.
    # For reference, measured tonight: nucleon 0.0:1 (one continuous stroke), solid bowl 0.7:1.
    if ratio > 1.0:
        problems.append(f"R5 dry travel: {travel_mm/1000:.1f}m of travel against "
                        f"{extrude_mm/1000:.1f}m extruded ({ratio:.1f}:1) — more distance in the "
                        f"air than laying material; find a continuously-extruded path")

    # R6  THE FILE MUST NAME THE FILAMENT IT WAS BUILT FOR, AND IT MUST BE THE ONE LOADED.
    # machine.check_spool() only WARNS at generation time, and a warning scrolls past. A file
    # built for one filament and printed with another is silently wrong: right geometry, wrong
    # temperature, wrong flow ceiling. Checked here, on the artifact, where it cannot scroll past.
    if _fmat and _fmat not in machine.SUSTAINED_FLOW_BY_MATERIAL:
        problems.append(f"R6 unknown material '{_fmat}': no maintained flow figure exists for it, "
                        f"so nothing about this file's flow can be checked")

    if _lh is None:
        problems.append("no '; LAYER_H=' stamp — R2 (Z ladder / floating lines) cannot be checked "
                        "at all. Regenerate with a current generator.")
    if not _fmat:
        problems.append("no '; MATERIAL=' stamp — R6 and the flow cap cannot be checked at all.")

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
