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


def first_layer_emitted(path, zerr, full=False):
    """WHERE THE FIRST LAYER ACTUALLY LANDS AND HOW WIDE, read off the emitted moves.

    R1 above asks where the first bead is COMMANDED, and on this machine that is not where it goes:
    the K2's Z zero sits `zerr` high, so a commanded Z0.100 with no correction lands at 0.250. The
    correction is a SET_GCODE_OFFSET line, and until 2026-08-06 nothing in this file had ever
    looked at one -- `grep -c SET_GCODE_OFFSET validate.py` returned 0 while every first-layer
    parameter in the project was being changed behind it.

    So this returns the two numbers that decide whether a first layer welds, both MEASURED:

      h1  = commanded Z of the body's first bead  +  the offset IN FORCE AT THAT BEAD  +  zerr
      w1  = (mm2 per mm of the moves at that Z)  /  h1

    THE OFFSET IN FORCE, NOT THE LAST ONE IN THE FILE. zladder.py sets its correction after G28 and
    then hands the machine back with `SET_GCODE_OFFSET Z=0` at the end; reading the file's last
    offset would report that ladder as printing at the machine's own uncorrected zero, which is the
    one thing it exists to avoid.

    `full=True` also returns every landed height in the file mapped to the width landed there,
    which is what makes a coupon citation checkable: a ladder that never tested 0.15 cannot excuse
    a part that prints at 0.15. It costs a full pass, so the default stops at the end of layer 1 --
    the buckets reach 85MB and the cheap answer is the one asked for on every run.

    Returns a dict; `z1` is None when there is no body bead to measure (R1 fails on that input, and
    R9 defers to it rather than printing a second verdict about the same absence)."""
    zoff = None                 # None means "the file never commanded one", which is not zero
    zoff_at_bead = None
    z = z1 = None
    x = y = None
    eabs, absE = 0.0, True
    body = False
    L1 = E1 = 0.0
    by_h = {}                   # landed height -> [path mm, filament mm]
    for ln in open(path):
        # The marker is a COMMENT, so it has to be read before comments are stripped -- reading it
        # off the stripped line found it in exactly zero of the 264 files in out/.
        if not body:
            body = 'BODY_START' in ln
        c = ln.split(';')[0].strip()
        if not c:
            continue
        if c.startswith('SET_GCODE_OFFSET'):
            _mo = re.search(r'\bZ=\s*(-?\d+(?:\.\d+)?)', c)
            if _mo:
                zoff = float(_mo.group(1))
            continue
        if c.startswith('M82'):
            absE = True
        elif c.startswith('M83'):
            absE = False
        elif c.startswith('G92'):
            _me = re.search(r'\bE(-?\d+(?:\.\d+)?)', c)
            if _me:
                eabs = float(_me.group(1))
        if c[:2] not in ('G0', 'G1'):
            continue
        _g = dict(re.findall(r'\b([XYZE])(-?\d+(?:\.\d+)?)', c))
        if 'Z' in _g:
            z = float(_g['Z'])
        nx = float(_g['X']) if 'X' in _g else x
        ny = float(_g['Y']) if 'Y' in _g else y
        de = 0.0
        if 'E' in _g:
            v = float(_g['E'])
            de = (v - eabs) if absE else v
            if absE:
                eabs = v
        # The prime is not the part -- R1 and R4 both draw this line, one definition reused.
        if (body and 'PRIME' not in ln.upper() and de > 0
                and None not in (x, y, nx, ny)):
            d = math.hypot(nx - x, ny - y)
            if d > 1e-9 and z is not None:
                h = round(z + (zoff or 0.0) + zerr, 4)
                if z1 is None:
                    z1, zoff_at_bead = z, zoff
                if abs(z - z1) < 1e-9:
                    L1 += d
                    E1 += de
                elif not full:
                    break
                r = by_h.setdefault(h, [0.0, 0.0])
                r[0] += d
                r[1] += de
        if 'X' in _g:
            x = nx
        if 'Y' in _g:
            y = ny
    out = {'zoff': zoff_at_bead, 'z1': z1, 'mm2': None, 'h1': None, 'w1': None, 'by_h': {}}
    if z1 is not None and L1 > 1e-9:
        out['mm2'] = E1 * FIL_AREA / L1
        out['h1'] = round(z1 + (zoff_at_bead or 0.0) + zerr, 4)
        if out['h1'] > 1e-9:
            out['w1'] = out['mm2'] / out['h1']
    out['by_h'] = {h: (v[1] * FIL_AREA / v[0]) / h
                   for h, v in by_h.items() if v[0] > 1e-9 and h > 1e-9}
    return out


COUPON_RE = re.compile(
    r'^;\s*COUPON=(\S+)\s+h1=([\d.]+)\s+w1=([\d.]+)\s+verdict=(\S+)\s+read=(\d{4}-\d{2}-\d{2})\s*$',
    re.M)


def sharp_angle_coverage(lines):
    """Return G3's selected move count, sharp turns, and worst spatial cluster.

    XYZ and E are modal G-code state.  Requiring a Z word on the same line as XY/E made ordinary
    layer bodies invisible to this rule.  Exempt declarations split runs so an angle is never
    invented across a move outside G3's jurisdiction.
    """
    runs, run = [], []
    x = y = z = None
    e, absolute_e, body = 0.0, True, False
    selected = 0
    for raw in lines:
        if 'BODY_START' in raw:
            body = True
            if run:
                runs.append(run); run = []
        code = raw.split(';')[0].strip()
        if code.startswith('M82'):
            absolute_e = True; continue
        if code.startswith('M83'):
            absolute_e = False; continue
        if code.startswith('G92'):
            me = re.search(r'\bE(-?\d+(?:\.\d+)?)', code)
            if me: e = float(me.group(1))
            continue
        if not code.startswith(('G0', 'G1')):
            continue
        g = dict(re.findall(r'\b([XYZE])(-?\d+(?:\.\d+)?)', code))
        nx = float(g['X']) if 'X' in g else x
        ny = float(g['Y']) if 'Y' in g else y
        nz = float(g['Z']) if 'Z' in g else z
        de = 0.0
        if 'E' in g:
            ev = float(g['E']); de = ev - e if absolute_e else ev
            e = ev if absolute_e else e + ev
        exempt = ('THIN CROSS' in raw.upper() or '; LINK' in raw
                  or ('; BRIDGE' in raw and ' pass ' in raw))
        deposited = (body and code.startswith('G1') and de > 1e-9
                     and None not in (x, y, nx, ny) and math.hypot(nx-x, ny-y) > 1e-9)
        if deposited and not exempt:
            selected += 1
            if not run:
                run = [(x, y)]
            run.append((nx, ny))
        elif run:
            runs.append(run); run = []
        x, y, z = nx, ny, nz
    if run:
        runs.append(run)

    sharp = []
    for points in runs:
        for i in range(1, len(points) - 1):
            ax, ay = points[i][0] - points[i-1][0], points[i][1] - points[i-1][1]
            bx, by = points[i+1][0] - points[i][0], points[i+1][1] - points[i][1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            if la < 0.05 or lb < 0.05:
                continue
            cv = max(-1.0, min(1.0, (ax*bx + ay*by) / (la*lb)))
            if math.degrees(math.acos(cv)) > 140.0:
                sharp.append(points[i])
    best = 0
    if sharp:
        cell, grid = 15.0, {}
        for sx, sy in sharp:
            key = (int(sx // cell), int(sy // cell)); grid[key] = grid.get(key, 0) + 1
        best = max(sum(grid.get((kx+dx, ky+dy), 0)
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                   for kx, ky in grid)
    return {'moves_examined': selected, 'sharp_turns': len(sharp), 'max_cluster': best}


def layer1_excuse(path, txt, h1, w1, zerr, lh):
    """May this file print an UNPROVEN first layer? Returns (excused, note).

    Two ways, and neither is a flag that means "trust me".

    1. '; COUPON=<file> h1=<mm> w1=<mm> verdict=welded read=<YYYY-MM-DD>' — a citation, checked
       four ways against artifacts rather than read. The coupon file must EXIST; its verdict must
       be `welded` (somebody thumb-peeled a corner and it fought back); the cited numbers must be
       the numbers THIS file actually lands, so a citation cannot drift away from the part it
       excuses; and those numbers must appear among the heights the COUPON ITSELF PRINTED, which is
       the clause that matters -- the ladder on the plate today sweeps 0.10 to 0.35 at 2.00mm wide,
       so it cannot excuse a 1.33mm weld at any height, and saying so is the whole point.

    2. '; Z_LADDER=1' — the coupon itself, which must be allowed to visit gaps nothing has proven
       because that is what it is for. FLOW_TEST=1 already sets this precedent for the flow cap.
       DECLARED AND COUNTED, like every other exception in RULES.md: the file must actually press
       at least three different heights at one width, measured off its own moves. A part presses
       exactly one, so a bucket that declares Z_LADDER is refused and says why.

    The count uses the file's OWN first-layer width and its OWN '; LAYER_H=' rather than constants:
    a ladder cell lands the same width as every other cell (the material scales with the gap, which
    is the correction that made zladder a ladder instead of a confound), and every cell sits inside
    the first two layers of the plate."""
    if re.search(r'^;\s*Z_LADDER=1\s*$', txt, re.M):
        _band = 2 * lh if lh else 0.5
        _all = first_layer_emitted(path, zerr, full=True)['by_h']
        _cells = sorted(h for h, w in _all.items() if h <= _band + 1e-9 and abs(w - w1) <= 0.05 * w1)
        if len(_cells) >= 3:
            return True, (f"'; Z_LADDER=1' is declared AND counted — this file presses "
                          f"{len(_cells)} different heights ({', '.join(f'{c:.2f}' for c in _cells)}"
                          f") at {w1:.2f}mm wide. A coupon is allowed to visit unproven gaps.")
        return False, (f"It declares '; Z_LADDER=1' but presses only {len(_cells)} height(s) at "
                       f"{w1:.2f}mm wide — that is a part, not a ladder, and the declaration does "
                       f"not survive being counted.")

    _m = COUPON_RE.search(txt)
    if not _m:
        if re.search(r'^;\s*COUPON=', txt, re.M):
            return False, ("It carries a '; COUPON=' line that does not parse — the stamp is "
                           "'; COUPON=<file> h1=<mm> w1=<mm> verdict=<word> read=<YYYY-MM-DD>', "
                           "and a citation nothing can check is not evidence.")
        return False, "It cites no coupon."
    _f, _ch1, _cw1, _verdict, _read = (_m.group(1), float(_m.group(2)), float(_m.group(3)),
                                       _m.group(4), _m.group(5))
    _cand = [os.path.join(os.path.dirname(os.path.abspath(path)), _f),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', _f), _f]
    _cp = next((c for c in _cand if os.path.isfile(c)), None)
    if _cp is None:
        return False, (f"It cites coupon '{_f}', and no such file exists next to it or in out/. A "
                       f"citation to a file nobody can open is the cheapest thing in this system "
                       f"to write and proves nothing.")
    if _verdict != 'welded':
        return False, (f"Its coupon citation reads verdict={_verdict}. Only 'welded' is evidence — "
                       f"a cell that was printed but not read, or read and not welded, excuses "
                       f"nothing.")
    if abs(_ch1 - h1) > 0.005 or abs(_cw1 - w1) > 0.05:
        return False, (f"Its coupon citation claims h1={_ch1:.3f} w1={_cw1:.2f}, but this file "
                       f"lands {h1:.3f} x {w1:.2f}. The citation has drifted from the part it is "
                       f"supposed to excuse.")
    _ch = first_layer_emitted(_cp, zerr, full=True)['by_h']
    _near = [(h, w) for h, w in _ch.items() if abs(h - _ch1) <= 0.005]
    if not _near:
        return False, (f"Coupon '{os.path.basename(_cp)}' never printed a {_ch1:.3f}mm layer at "
                       f"all — it laid {', '.join(f'{h:.2f}' for h in sorted(_ch)[:8])}"
                       f"{'...' if len(_ch) > 8 else ''}. A coupon can only excuse the gap it "
                       f"tested.")
    if not any(abs(w - _cw1) <= 0.05 for _, w in _near):
        return False, (f"Coupon '{os.path.basename(_cp)}' printed {_ch1:.3f}mm, but at "
                       f"{', '.join(f'{w:.2f}' for _, w in _near)}mm wide, not the {_cw1:.2f}mm "
                       f"cited. Height and width are one weld, not two settings.")
    return True, (f"coupon '{os.path.basename(_cp)}' printed {_ch1:.3f}mm x {_cw1:.2f}mm and was "
                  f"read as welded on {_read}, and those are the numbers this file lands.")


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
    travel_mm = extrude_mm = hop_mm = 0.0
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
                # HOPS BETWEEN OBJECTS ARE ALREADY LICENSED, so R5 must not also count them.
                # On a 12-up plate of small parts the head legitimately crosses the bed once per
                # part per layer; totalling those made R5 report 1.6:1 and refuse a correct file.
                # The parts themselves are each one continuous stroke, which is what R5 protects.
                if '; HOP' in raw or '; PRIME' in raw:
                    hop_mm += d
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
            if 'Z' in s and 'E' not in s and '; HOP' not in raw and '; LINK' not in raw:
                # A HOP's lift is temporary and drops straight back — treating it as a new layer
                # floor makes the matching drop look like a plough. Layer changes set the floor;
                # hops do not. Nor do LINK ride-overs: a gentle Z jump over an existing strand
                # (Oleg's "pause extrusion" crossings) is an E-less G1 X Y Z, which otherwise looks
                # exactly like a layer-change Z move and would record the CREST as the floor —
                # making the descent back to the real floor read as a plough. It is not a layer
                # change; the strand below already holds that ground.
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
        # MATERIAL PROXIMITY, NOT BOUNDING BOXES. Bboxes are the wrong frame for CONCAVE parts:
        # an L-shaped pole hook interlocks its neighbour's box by ~3mm while the material stays
        # 8mm apart — 29 phantom overlaps on a plate whose hooks provably print disjoint (the
        # measuring-frame lesson, fourth instance today). The crash being guarded against is
        # the NOZZLE dragging through a finished part, so measure what the nozzle does: any
        # extruding point of a later part within 1.5mm of an earlier part's deposited points.
        _pparts = []      # (label, [points])
        _cur, _pp = "part 1", []
        for l in _lines:
            if l.startswith('; ---- part'):
                if _pp:
                    _pparts.append((_cur, _pp))
                _cur = l.strip('; -').split(':')[0].strip(); _pp = []
            # deposits only — travels/park excluded; the PRIME purge is off-part by design
            if 'PRIME' in l.upper():
                continue
            _m = re.match(r'^G1 .*X([-\d.]+) Y([-\d.]+).*E[\d.]', l)
            if _m:
                _pp.append((float(_m.group(1)), float(_m.group(2))))
        if _pp:
            _pparts.append((_cur, _pp))
        _PCELL = 1.5
        _pgrid = {}
        _clash = []
        for _lab, _pp in _pparts:
            _hit = None
            for _x2, _y2 in _pp:
                _gx, _gy = int(_x2 // _PCELL), int(_y2 // _PCELL)
                for _dx in (-1, 0, 1):
                    for _dy in (-1, 0, 1):
                        for _ol, _ox2, _oy2 in _pgrid.get((_gx + _dx, _gy + _dy), ()):
                            if (_x2-_ox2)**2 + (_y2-_oy2)**2 < _PCELL**2:
                                _hit = (_ol, _x2, _y2); break
                        if _hit: break
                    if _hit: break
                if _hit: break
            if _hit:
                _clash.append((_hit[0], _lab, _hit[1], _hit[2]))
            for _x2, _y2 in _pp:
                _pgrid.setdefault((int(_x2 // _PCELL), int(_y2 // _PCELL)), []).append((_lab, _x2, _y2))
        if _clash:
            _f = _clash[0]
            problems.append(
                f"{len(_clash)} sequentially-printed part(s) deposit within {_PCELL}mm of an "
                f"earlier part's material — e.g. '{_f[1]}' at ({_f[2]:.1f},{_f[3]:.1f}) onto "
                f"'{_f[0]}'. The nozzle would drag through the finished part.")
        else:
            print(f"  sequential: {len(_pparts)} parts, material never within {_PCELL}mm of an "
                  f"earlier part")

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
    # A DECLARED WAVE WALL DESCENDS ON PURPOSE. A sinusoid-Z wall (bucket.py) drops at up to
    # WAVE_SLOPE dz/dxy, so within one cell the strand legitimately descends slope * cell-diagonal
    # below ITS OWN crest — 0.40mm at slope 0.47, over this check's 0.35 threshold: 64 false
    # dives on a file whose lap-to-lap weld gap is provably >= one layer height everywhere.
    # The raised threshold applies ONLY after the '; WALL_START' marker, and stays UNDER one
    # layer height — a real collision with the lap below reads >= layer_h and still fails.
    _mws = re.search(r'^; WAVE_SLOPE=([\d.]+)', '\n'.join(_lines[:60]), re.M)
    _wall_i = next((i for i, l in enumerate(_lines) if l.startswith('; WALL_START')), None)
    _wave_thr = 0.35
    if _mws and _wall_i is not None:
        _wlh = re.search(r'^; LAYER_H=([\d.]+)', '\n'.join(_lines[:60]), re.M)
        _wave_thr = max(0.35, min((float(_wlh.group(1)) if _wlh else 0.6) * 0.9,
                                  float(_mws.group(1)) * _CELL * 1.42 + 0.1))
        print(f"  wave wall declared (slope {_mws.group(1)}): in-cell dive threshold "
              f"{_wave_thr:.2f}mm after WALL_START (0.35 before)")
    # SELF-DESCENT IS NOT A DIVE, AND DEPTH CANNOT TELL THEM APART — TIME CAN. A steep wave
    # fall (slope 1.07 at H=2.4) descends ~0.9mm within one cell's reach ALONG ITS OWN STRAND,
    # past any threshold capped under a layer height; meanwhile a REAL collision at a 0.3mm
    # landing gap would need a threshold UNDER 0.3 to catch. The discriminator is the path
    # odometer: self-descent is against material laid millimetres ago, a real collision is
    # against a lap laid a full circumference ago. Material older than _SELF_MM of path keeps
    # the full 0.35 sensitivity; younger material is the strand itself.
    _SELF_MM = 12.0
    _topo = {}
    _pz = 0.0
    _px = _py = None
    _odo = 0.0
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
            _seg = math.hypot(_nx - _px, _ny - _py)
            _n = min(64, max(1, int(_seg / _CELL)))  # bounded
            _worst = None
            for _k in range(_n + 1):
                _t = _k / _n
                _cx = int((_px + (_nx - _px) * _t) / _CELL)
                _cy = int((_py + (_ny - _py) * _t) / _CELL)
                _cz = _pz + (_nz - _pz) * _t
                _prev = _topo.get((_cx, _cy))
                _thr = _wave_thr if (_wall_i is not None and _i > _wall_i) else 0.35
                if _prev is not None and _prev[0] > 0.3 and _prev[0] - _cz > _thr \
                        and _odo + _seg * _t - _prev[1] > _SELF_MM:
                    if _worst is None or _prev[0] - _cz > _worst[2] - _worst[1]:
                        _worst = (_i + 1, round(_cz, 3), round(_prev[0], 3))
                if _ext and (_prev is None or _cz > _prev[0]):
                    _topo[(_cx, _cy)] = (_cz, _odo + _seg * _t)
            if _worst and _ext:
                _dives.append(_worst)
            if _ext:
                _odo += _seg
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
    _xall = []
    # THE PRIME MUST NOT SET THE YARDSTICK, WHATEVER IT IS METERED AT.
    # Taking the nominal bead from the running maximum let the prime line define it — so on a
    # single-layer file every real move measured as starved. Only body moves define what normal
    # looks like, and the boundary is '; BODY_START' below.
    # This comment used to say "THE PRIME IS DELIBERATELY HEAVY", which was true of the old
    # hand-rolled primes (2.4x to 5.0x the body's own layer-1 rate) and stopped being true on
    # 2026-08-06 when machine.prime() started metering from machine.layer1_rate at a bounded 1.2x.
    # The CODE was right either way because it gates on _inbody; the sentence was a claim about the
    # artifact that the artifact no longer supported, which is its own kind of stale.
    _inbody = False
    for _i, _l in enumerate(_lines):
        if '; BODY_START' in _l: _inbody = True
        _b = _l.split(';')[0].strip()
        # G92 RESETS THE E AXIS, AND NOT HONOURING IT BLINDED THIS GUARD OVER LAYER 1.
        # _pe2 is a running MAX of E, which is right for catching a retraction and wrong across a
        # reset: every generator here primes to E20-E30 and then writes `G92 E0`, so _pe2 stayed at
        # the prime's value while the body counted up from zero. Two things followed, and the second
        # is the serious one. (1) The move where the body's cumulative E finally crossed the prime's
        # value measured (E - prime) instead of (E - previous) and was reported STARVED -- a
        # phantom, 40mm at 0.005mm2, on a file whose thinnest real move was 0.100. (2) EVERY body
        # move before that crossing was skipped by the `_ne > _pe2` test and never checked at all:
        # 108 of 532 moves in one file, and they are the FIRST 108 -- layer 1, the one layer whose
        # adhesion this whole project turns on. A file whose entire body uses less filament than its
        # prime was never checked by this guard at all and still printed a green tick.
        if _b.startswith('G92'):
            _mg = re.search(r'E([-\d.]+)', _b)
            if _mg:
                _pe2 = float(_mg.group(1))
            continue
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
                if _inbody:
                    _xall.append((_i + 1, _d, _x))
        if _nx is not None: _px2, _py2 = _nx, _ny
        _pe2 = max(_pe2, _ne)
    # THE FILE'S OWN BEAD IS THE MEDIAN, NOT THE MAX. The nominal used to be a running max of
    # mm2-per-XY-mm, and a single legitimate near-vertical move (a gap-close onto a lifted seam:
    # 0.4mm of Z over 0.055mm of XY = 8.8mm2/mm) inflated it 7x — then EVERY normal move in the
    # file read "under a quarter of the bead" and a correct file failed with 15 phantom starved
    # moves. The median is immune to the tails on both sides; the real starved threads this
    # guard exists for (a 0.02mm2 drag) sit far below a quarter of any sane median.
    if _xall:
        _med = sorted(x for _, _, x in _xall)[len(_xall) // 2]
        _starved = [(_i2, _d2, _x2, _med) for (_i2, _d2, _x2) in _xall
                    if _x2 < 0.25 * _med and _d2 > 2.0]
    # thin inter-tile links are deliberate (hilbert --tile) and are stamped; everything else is not
    # Deliberate thin links are TAGGED in the source that emits them; anything untagged that is
    # starved is a bug. Tagging beats loosening the threshold — a looser threshold would have let
    # the 18mm prime thread through, which is the exact defect this guard exists to catch.
    _starved = [t for t in _starved
                if '; LINK' not in _lines[t[0] - 1] and '; RETRACE' not in _lines[t[0] - 1]
                and '; THIN CROSS' not in _lines[t[0] - 1]]
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
    _ply = {}          # the same points, split by part: {label: {z: [pts]}}
    _zz = 0.0
    _cpart = "part 1"
    for _l in _lines:
        if _l.startswith('; ---- part'):
            _cpart = _l.strip('; -').split(':')[0].strip()
        _b = _l.split(';')[0]
        _m = re.search(r'Z([\d.]+)', _b)
        if _b.startswith(('G0 ', 'G1 ')) and _m: _zz = round(float(_m.group(1)), 3)
        _mm = re.match(r'^G1 .*X([-\d.]+) Y([-\d.]+).*E[\d.]', _b)
        if _mm:
            # DECLARED IN-AIR REGIMES ARE FLAGGED, NOT DROPPED. A '; BRIDGE' / '; THIN CROSS' /
            # '; LINK' move is deliberately airborne, declared in the header and judged by its own
            # gates (R4e here, S4's span ledger in send.py) -- the run-length measure below must
            # not re-refuse a span those gates already own. They still contribute their endpoints
            # as MATERIAL (the next layer may sit on a bridge), so they stay in the point list.
            _air = ('BRIDGE' in _l) or ('THIN CROSS' in _l) or ('; LINK' in _l)
            _pt = (float(_mm.group(1)), float(_mm.group(2)), _air)
            _ly.setdefault(_zz, []).append(_pt)
            _ply.setdefault(_cpart, {}).setdefault(_zz, []).append(_pt)
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
        _ogroups = []
    elif _seq and len(_ply) > 1:
        # ON A SEQUENTIAL PLATE, A LAYER IS SUPPORTED BY ITS OWN PART — NOT BY ITS Z BIN.
        # Binning Z across the whole file assumes every part shares one ladder. A sequential plate
        # breaks that assumption outright: parts printed one after another can sit at different
        # heights, so the bin above a part's layer holds ANOTHER part's material, somewhere else on
        # the plate entirely. Measured on presstest (eight independent ribbons lying flat on the
        # glass, nothing stacked anywhere): "100% of layer Z0.15 has no material within one bead of
        # it on layer Z0.1" — a true statement about two unrelated ribbons and a meaningless one
        # about support. Wrong FRAME, not a wrong threshold, which is the fourth time that same
        # mistake has produced a phantom failure in this file. The guard's question is "does this
        # layer sit on the layer below it IN THIS PART", so that is what is now asked.
        _ogroups = [(_lab, sorted(_d)) for _lab, _d in _ply.items()]
    else:
        _ogroups = [(None, sorted(_ly))]
    _bead = 1.2
    _mb = re.search(r'bead ([\d.]+)x', open(path).read()[:4000])
    if _mb: _bead = float(_mb.group(1))
    # THE FRAME IS RUN LENGTH, NOT FRACTION-OF-POINTS. Corrected 2026-08-07 on Oleg's instruction
    # ("correct the validate", choosing a 4mm floor lattice), and the correction cuts BOTH ways:
    #   * The old ">5% of points unsupported" REFUSED a deliberate lattice whose unsupported runs
    #     are 3-4mm -- on a machine where machine.PROVEN_AIR_MM = 16.8mm of open air is PROVEN to
    #     pull taut as a bridge. A 5.0mm-pitch 5-layer floor was refused at 23% and the floor was
    #     densified to 2.5 in response, adding ~30g a part, when its 4.18mm runs were never the
    #     thing that fails. Wrong frame, so the threshold punished physics that works.
    #   * The same 5% PASSED a genuinely floating line: one 40mm run in a dense 10k-point layer is
    #     0.4% of points and sailed through. The quantity that decides whether material stays up is
    #     how LONG it hangs in air before it reaches support again -- a run, not a ratio.
    # So: consecutive unsupported points along the printed path accumulate into runs; a supported
    # point or a >3mm jump in the sampled sequence (a path discontinuity -- one long move, whose
    # air is its OWN declared business) closes the run; the longest run is judged against the
    # measured bridge evidence. Declared in-air moves (BRIDGE / THIN CROSS / LINK) are excluded
    # from runs -- their spans are owned by R4e and send.py's S4 ledger -- but their endpoints
    # still count as material for the layer above.
    _worstz, _worstf, _opairs = None, 0.0, 0
    _worstrun, _worstrunz = 0.0, None
    for _plab, _zs in _ogroups:
        _src = _ply[_plab] if _plab is not None else _ly
        # TWO LAYERS IS ONE PAIR, AND ONE PAIR IS THE WHOLE QUESTION. This read `<= 2` until
        # 2026-08-15, so a part with exactly two layers -- layer 2 sitting on layer 1, which is
        # precisely "does this layer sit on the layer below it" -- was skipped, and the file then
        # printed "no part in this file has two layers" about a plate where every part had two.
        # A guard that declines to look and says so in words that mean the opposite is worse than
        # one that fails: the sentence reads like a clean bill of health. Found on the first
        # 2-layer hooks this lane ever printed.
        if len(_zs) < 2:
            continue
        for _a, _bz in zip(_zs, _zs[1:]):
            _A = _src[_a]
            _B = _src[_bz]
            if len(_A) < 3 or len(_B) < 3: continue
            _opairs += 1
            # INDEX THE LOWER LAYER IN FULL. Sampling it to 250 points spread over a 315mm plate
            # put the nearest sample far from every query point and reported 94% of a perfectly
            # supported layer as overhanging — the same measure-the-easy-quantity error this guard
            # exists to catch. A spatial hash at bead resolution is exact enough and O(n).
            # THE PRESSED FIRST LAYER IS FAR WIDER THAN A BEAD. It carries the body's mm2 into
            # a 0.1mm gap, so it lands at mm2/PRESS_HARD -- about 9mm from a 1.5mm bead. Measuring
            # support against a one-bead radius then reports a fully-covered layer 2 as 30%
            # overhanging. A false positive is how a guard gets switched off, so the support
            # radius uses the LOWER layer's real width when it is the pressed first one.
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
            _un = 0
            _run, _runmax = 0.0, 0.0
            _pprev = None            # previous NON-declared-air point, for run accumulation
            for _p in _B:
                if _p[2]:            # declared in-air move: not this gate's jurisdiction
                    _pprev = None    # and a discontinuity for run purposes
                    continue
                _s = _supported(_p)
                if not _s:
                    _un += 1
                    if _pprev is not None:
                        _d4 = math.hypot(_p[0] - _pprev[0], _p[1] - _pprev[1])
                        _run = (_run + _d4) if _d4 <= 3.0 else 0.0
                    _runmax = max(_runmax, _run)
                else:
                    _run = 0.0
                _pprev = _p
            _nB = sum(1 for _p in _B if not _p[2])
            _frac = _un / _nB if _nB else 0.0
            if _frac > _worstf: _worstf, _worstz = _frac, (_a, _bz, _plab)
            if _runmax > _worstrun: _worstrun, _worstrunz = _runmax, (_a, _bz, _plab)
    if _worstrun > machine.PROVEN_AIR_MM:
        problems.append(
            f"OVERHANG: a continuous {_worstrun:.1f}mm run of layer Z{_worstrunz[1]} has no "
            f"material within one bead ({_bead}mm) of it on layer Z{_worstrunz[0]}"
            f"{' in ' + _worstrunz[2] if _worstrunz[2] else ''} — longer than the "
            f"{machine.PROVEN_AIR_MM:g}mm of open air this machine has ever been seen to bridge "
            f"(machine.PROVEN_AIR_MM). That material is being extruded onto nothing with no "
            f"evidence it can span the gap. A declared bridge belongs on its own schedule "
            f"('; BRIDGE'), judged by R4e and the send ledger; an undeclared run this long is a "
            f"floating line.")
    elif _ogroups and not _opairs:
        # SAY IT OUT LOUD. A check that had nothing to measure must not read as a check that passed
        # — that is the same silence the missing-stamp failures were added to break.
        print(f"  overhang: nothing to check — every one of the {len(_ogroups)} part(s) in this "
              f"file is a SINGLE layer, so nothing is stacked on anything")
    elif _opairs:
        print(f"  overhang: worst unsupported RUN {_worstrun:.1f}mm (proven bridgeable: "
              f"{machine.PROVEN_AIR_MM:g}mm); worst layer-pair fraction {_worstf*100:.0f}% "
              f"across {_opairs} pair(s) — fraction is REPORTED, not judged: a lattice is a "
              f"choice, and run length is what decides whether material stays up"
              f"{', checked per part' if len(_ogroups) > 1 else ''}")

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
    # HOMING IS A COMMAND, NOT A WORD IN A COMMENT. This grepped the raw source until 2026-08-15,
    # so a file that deliberately does NOT home and explains why in a comment -- "homing here costs
    # a full 81-point probe" -- handed itself a homing tick by naming the command it refuses to
    # run, and the deliberate-no-home warning never printed. Read the code, not the prose: the same
    # mistake as scoring a move against a stale position, one line further down the same file.
    _code_src = '\n'.join(_l.split(';')[0] for _l in src.split('\n'))
    if 'G28' not in _code_src and 'START_PRINT' not in _code_src:
        # A deliberate no-home file is a real tier (back-to-back iteration on an already-homed
        # machine). Klipper refuses to move an unhomed axis, so this fails SAFELY rather than
        # crashing — it is a warning, not a defect. Unmarked missing-home is still a failure.
        if 'NO HOME' in src:
            warns.append("no homing — deliberate. Machine must still be homed from a previous run.")
        else:
            problems.append("never homes (no G28 and no START_PRINT macro)")
    # R5 measures the WORK's continuity, so licensed hops are excluded from the numerator.
    ratio = max(0.0, travel_mm - hop_mm) / max(extrude_mm, 1e-9)
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
            # A BARE FEEDRATE MAY CARRY A COMMENT, and until 2026-08-07 this regex required the line
            # to END at the number. So `G1 F1050 ; BRIDGE SLOWED to 17.5mm/s` was invisible here,
            # `_f` stayed at whatever came before it, and every following move was scored at a STALE
            # speed -- reporting 157 mm3/s for a move actually running at 55. It fails in the
            # direction that raises a false alarm on a correct file, but the same staleness would
            # UNDER-report a move that sped up, which is the direction that matters. Any generator
            # writing an explained feedrate change was affected, not just the one that found it.
            _mf = re.match(r'G1 F(\d+)\s*(?:;.*)?$', _ln.rstrip())
            if _mf:
                _f = float(_mf.group(1)) / 60.0
            # THE POSITION MUST FOLLOW EVERY MOVE, NOT ONLY THE EXTRUDING ONES. Until 2026-08-15
            # `_pp` was updated only on lines this regex matched, so a G0 moved the head and this
            # loop did not notice: the first extruding move after ANY travel was scored against
            # wherever the previous EXTRUSION ended. It fails in both directions and the dangerous
            # one is silent -- a hop away from the part leaves a stale distance LARGER than the real
            # move, so a genuinely over-flowing first move after a travel reads low and passes. The
            # loud direction found it: a 30-up plate of hooks whose index marks are one move each
            # reported 77 mm3/s on moves emitting exactly 49.25, because consecutive marks sit 7mm
            # apart and each mark is 9mm long. A flow guard whose failure text reads "a position
            # variable is probably stale" was itself carrying one.
            _c0 = _ln.split(';')[0]
            if _c0.startswith(('G0 ', 'G1 ')):
                _tx = re.search(r'X([-\d.]+)', _c0)
                _ty = re.search(r'Y([-\d.]+)', _c0)
                _tz = re.search(r'Z([-\d.]+)', _c0)
                if _tx and _ty:
                    _pp = (float(_tx.group(1)), float(_ty.group(1)),
                           float(_tz.group(1)) if _tz else (_pp[2] if _pp else 0.0))
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
    # R8 — THE DECLARED FLOW MUST MEET THE MATERIAL'S FIGURE, OR THE FILE MUST SAY WHY NOT.
    # Oleg, 2026-07-27, the FIFTH flow incident: "when i said go slow you killed the flow with
    # it. why our guard to keep flow constant did not worked for the 5th time aleady?!?"
    # The structural answer: R4 checks the file against ITS OWN '; FLOW=' stamp — a generator
    # that honestly stamps a derated number is self-consistent and sails through. NOTHING
    # compared the stamp to the material's measured figure, so a --speed 10 cap silently
    # re-declared 60 as 12 and every guard nodded. Slow is allowed (air-cooling, tests);
    # SILENT slow is not: below 80% of the material+printer cap the file must carry an
    # explicit '; FLOW_DERATE=<reason>' stamp, or it fails here.
    _m_mat = re.search(r'^; MATERIAL=(\S+)', _rules_txt, re.M)
    _m_prn = re.search(r'^; PRINTER=(\S+)', _rules_txt, re.M)
    if _decl_flow and _m_mat:
        _r8cap = machine.flow_cap(_m_mat.group(1), _m_prn.group(1) if _m_prn else None)
        _m_der = re.search(r'^; FLOW_DERATE=(.+)$', _rules_txt, re.M)
        if _r8cap and _decl_flow < 0.8 * _r8cap:
            if _m_der:
                print(f"  R8: flow derated to {_decl_flow:g} of the {_r8cap:g} mm3/s cap — "
                      f"DECLARED: {_m_der.group(1).strip()}")
            else:
                problems.append(
                    f"R8 flow floor: this file declares {_decl_flow:g} mm3/s against the "
                    f"{_r8cap:g} mm3/s figure for {_m_mat.group(1)} — a {100*_decl_flow/_r8cap:.0f}% "
                    f"operating point with NO '; FLOW_DERATE=' stamp. R4 only checks the file "
                    f"against its own declaration; the VALUE needs a declared reason. Slow is "
                    f"allowed, silent slow is not.")
    _xr, _yr, _er, _fr, _zr = None, None, 0.0, None, 0.0
    _z0 = 0.0
    # HOISTED. These two searches scan the WHOLE file, and they were inside the per-line loop
    # below -- 199,560 re.search calls on an 8,000-line file, 16.9 s of the 17.5 s total, and
    # quadratic in file size. That is why the 372,000-line bucket could not be validated at all.
    # A guard nobody can afford to run is a guard that does not run.
    _m_l1 = re.search(r'^; SPEED_LAYER1=([\d.]+)', _rules_txt, re.M)
    _l1v_decl = float(_m_l1.group(1)) if _m_l1 else None
    _m_pv = re.search(r'^; PRESSED_LAYER1=([\d.]+)', _rules_txt, re.M)
    _pv_decl = float(_m_pv.group(1)) if _m_pv else None
    _m_pkt = re.search(r'^; SPEED_POCKET=([\d.]+)', _rules_txt, re.M)
    _pkt_decl = float(_m_pkt.group(1)) if _m_pkt else None
    _m_cnr = re.search(r'^; SPEED_CORNER=([\d.]+)', _rules_txt, re.M)
    _cnr_decl = float(_m_cnr.group(1)) if _m_cnr else None
    # R4e's declaration. A BRIDGE IS A DECLARED SECOND FLOW REGIME, so it is stamped as the
    # CROSS-SECTIONS the file intends to lay, not as multipliers: mm2 per mm of path is measurable
    # straight off the emitted E and the emitted distance, while a multiplier can only be checked
    # by re-running the arithmetic that produced it, which is not an independent check.
    _m_bmm2 = re.search(r'^; BRIDGE_MM2=([\d.,]+)', _rules_txt, re.M)
    _bdecl = sorted(float(v) for v in _m_bmm2.group(1).split(',')) if _m_bmm2 else None
    # R3d's declaration. A SLOWED BRIDGE IS A DECLARED SPEED REGIME, and it is a LIST rather than a
    # single value because each flow multiplier needs its own speed to stay under the same cap: at
    # layer 0.48 a 4x accent lands at 34.9 mm/s and an 8x rim at 17.5, from one flow ceiling.
    # SPEED_POCKET and SPEED_CORNER are single-valued because one slowdown covers their whole
    # feature; a bridge schedule is several features at once.
    _m_bspd = re.search(r'^; SPEED_BRIDGE=([\d.,]+)', _rules_txt, re.M)
    _bspd_decl = sorted(round(float(v), 1) for v in _m_bspd.group(1).split(',')) if _m_bspd else None
    _spd, _flw, _nlink, _pspd, _cspd = {}, [], 0, {}, {}
    _bspd = {}                  # speed histogram of the BRIDGE moves alone, for R3d
    _nthin = 0
    _bvals = []
    _xspd = {}
    _area = math.pi * (1.75 / 2) ** 2
    for _raw in _rules_txt.splitlines():
        _code = _raw.split(';')[0].strip()
        _isprime = 'PRIME' in _raw.upper()
        if not _code.startswith(('G0', 'G1')):
            continue
        _g = dict(re.findall(r'\b([XYEFZ])(-?\d+(?:\.\d+)?)', _code))
        _z0 = _zr
        if 'Z' in _g: _zr = float(_g['Z'])
        if 'F' in _g:
            _fr = float(_g['F'])
        # LINK MOVES ARE DECLARED, NOT ASSUMED. solid.py labels its contour-to-contour connectors
        # '; LINK thin' and deliberately meters them down: they cross ground the NEXT contour will
        # cover, so a full bead there lays a second bead at the same Z, doubles the height and the
        # nozzle drags through it on the next layer. That is a real reason, and the generator
        # states it in the file rather than relying on the checker to guess. They are exempt from
        # R4 but COUNTED and reported, so an exemption can never hide a growing problem.
        # THIN CROSS IS THE SAME SHAPE AS LINK AND EARNS THE SAME TREATMENT.
        # Oleg, 2026-08-05: "why we ever want to fly without anything coming out? Are not we
        # releasing tiny all the time at least". There is no retraction in this project, so a "dry"
        # travel was never dry: it oozed, and the web in the printed coupon IS that ooze. bucket
        # crossings now meter it at a stated fraction of the body rate, turning an uncontrolled leak
        # into a strand that was chosen. The generator STAMPS each one '; THIN CROSS <n>%'.
        # R4 cannot tell a chosen strand from a starved extruder by arithmetic alone, which is the
        # whole reason it refused these. It does not have to: the file declares them, and they are
        # COUNTED and reported below, so an exemption can never hide a growing problem.
        _isthin = 'THIN CROSS' in _raw.upper()
        if _isthin:
            _nthin += 1
            if 'F' in _g:
                _xspd[float(_g['F']) / 60.0] = _xspd.get(float(_g['F']) / 60.0, 0) + 1
        _islink = 'LINK' in _raw.upper() or _isthin
        if _islink and not _isthin:
            _nlink += 1
        # THE BORE SLOWDOWN IS A DECLARED REGIME, SO IT MUST BE CHECKED, NOT IGNORED. Pocket moves
        # (Oleg's "4x slow down rthere") are LINK-tagged, so the body-speed histogram below skips
        # them — correct, they are a second regime. But "skipped" must not mean "unverified": the
        # slowdown silently failing to apply is the exact 5x-repeated flow-guard failure. So the
        # pocket moves' own speed is collected here and checked against ; SPEED_POCKET (R3b below).
        _ispocket = _islink and 'POCKET' in _raw.upper()
        if _ispocket and 'X' in _g and 'E' in _g and _fr:
            _psp = round(_fr / 60.0, 1)
            _pspd[_psp] = _pspd.get(_psp, 0) + 1
        # THE CORNER SLOWDOWN IS A THIRD DECLARED REGIME, checked the same way as the pocket. Sharp
        # corners run at SPEED_CORNER (LINK-tagged '; LINK corner slow'), so the body histogram skips
        # them; their own speed is collected here and verified against ; SPEED_CORNER by R3c below.
        _iscorner = _islink and 'CORNER' in _raw.upper()
        if _iscorner and 'X' in _g and 'E' in _g and _fr:
            _csp = round(_fr / 60.0, 1)
            _cspd[_csp] = _cspd.get(_csp, 0) + 1
        # A BRIDGE IS A FOURTH DECLARED REGIME, and it is the only one that meters flow UP.
        # Oleg, 2026-08-06: "the features are all bridges", "Just different extrusion volume" —
        # a solid line, an accent band and the top rim are ONE move across the gap at 2x/4x/8x the
        # body's bead, which in air makes a thicker rod. R4 refuses that on sight and it is RIGHT
        # to: an unexplained 8x is an over-extrusion bug. So it is declared as '; BRIDGE_MM2=' and
        # each move stamped '; BRIDGE <n>x <mm2>mm2', and R4e below MEASURES the emitted moves
        # against the declaration. Exempt from R4 ONLY when declared, never blanket, and COUNTED.
        _isbridge = 'BRIDGE' in _raw.upper() and 'X' in _g and 'E' in _g
        # WHICH MOVES ARE LAYER 1 IS A QUESTION ABOUT Z, NOT ABOUT SPEED — and keying it on speed
        # turned R3 and R4 off entirely for this whole project. Layer 1 is held out of the speed and
        # flow histograms because it is deliberately a different bead. The old test asked "does this
        # move run at the declared SPEED_LAYER1", which was written when layer 1 was slower than the
        # body. It is not slower any more: machine.py's FIRST_LAYER_SPEED = CONSTANT_SPEED, Oleg's
        # "50 is our north star for moving", so a compliant file runs layer 1 AND the body at the
        # same 50 -- and every move in the file then matched, so _spd and _flw were never filled and
        # R3/R4 produced no verdict at all. Not a weakened check: an ABSENT one, on every file this
        # project emits, and absent silently, which is the exact failure validate.py's own header
        # condemns. PROVEN on a 2-layer hook plate: one layer-2 move starved to 40% of the declared
        # flow passed clean with no R4 line.
        # So ask Z when the file says where layer 1 is, and keep the speed heuristic only for files
        # that carry no '; PRESSED_LAYER1=' to ask.
        if _pv_decl is not None:
            _isl1 = abs(_zr - _pv_decl) < 1e-6
        else:
            _isl1 = bool(_l1v_decl) and _fr is not None and abs(_fr / 60.0 - _l1v_decl) < 0.6
        if 'X' in _g and 'E' in _g and _xr is not None and _fr and not _isprime \
                and not _isl1:
            # FLOW IS PER MM OF PATH, AND THE PATH IS 3D. F is a 3D feedrate in Klipper, so the
            # volumetric rate through the nozzle is de*A / (d3/v). Measuring against the XY
            # projection over-reads any climbing move by d3/dxy — harmless on flat prints
            # (dz~0) but a steep wave wall (slope 1.07) read +46% and failed R4 while
            # delivering EXACTLY constant flow through the nozzle.
            _d = math.hypot(float(_g['X']) - _xr, float(_g['Y']) - _yr, _zr - _z0)
            _de = float(_g['E']) - _er
            if _d > 0.05 and _de > 0:
                _sp = round(_fr / 60.0, 1)
                # SPEED constancy exempts ONLY declared regimes (POCKET here, LAYER1
                # handled below), NOT every LINK. A plain '; LINK' move at a second
                # feedrate otherwise passed R3 silently (review 2026-07-29): R3 dropped
                # all LINK from the histogram and R3b only saw POCKET-tagged ones. Plain
                # LINK connectors run at body speed so they enter harmlessly; a genuine
                # second speed on them now fails R3.
                if not _ispocket and not _iscorner:
                    _spd[_sp] = _spd.get(_sp, 0) + 1
                # A BRIDGE STAYS IN THE SPEED HISTOGRAM ON PURPOSE. It runs at the body speed and
                # is meant to; only its FLOW is a second regime. If a generator ever slowed one to
                # buy volume, R3 must see it rather than a bridge exemption swallowing it.
                if _isbridge:
                    _bvals.append((_de * _area) / _d)          # mm2 per mm of path
                    # AND ITS SPEED, SEPARATELY, so R3d can check a declared slowdown against the
                    # moves that claim it. Collected for EVERY bridge, not only slow ones: a
                    # histogram that only recorded the exceptions could not tell "all bridges run
                    # at the body speed" from "no bridge move was seen at all".
                    _bspd[_sp] = _bspd.get(_sp, 0) + 1
                # FLOW: all LINK stay exempt — they legitimately meter flow down. A declared
                # bridge is exempt too; an UNDECLARED one is not, and R4 fails it as before.
                if not _islink and not (_isbridge and _bdecl):
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
        _xceil = float(_decl_x0.group(1)) if (_decl_x0 := re.search(
            r'^; SPEED_CROSS=([\d.]+)', _rules_txt, re.M)) else None
        _fast = {k: v for k, v in _spd.items()
                 if k > _ceil + 0.6 and not (_xceil and abs(k - _xceil) < 0.6)}
        if _fast:
            problems.append(f"R3 speed ceiling: {sum(_fast.values())} extruding moves exceed the "
                            f"{_ceil:g} mm/s ceiling (found {sorted(_fast)[:4]})")
        # A DECLARED FIRST-LAYER SPEED IS LEGITIMATE. Oleg, 2026-07-27: "lets also try first layer
        # normal speed and ret layers double speed". Layer 1 is already a different cross-section
        # (pressed to PRESS_HARD), so it is a different regime, not a wobble inside one. What R3
        # protects is constancy WITHIN the body. The file must declare it: '; SPEED_LAYER1='.
        # A DECLARED CROSSING REGIME IS THE SAME ARGUMENT AS THE DECLARED FIRST LAYER, and it has
        # to be removed BEFORE the layer-1 test, which keys on there being exactly two speeds.
        # An in-air strand between two towers is not deposition onto structure: nothing is being
        # laid ONTO anything, so the bead-width and adhesion reasons behind the 50 north star do
        # not apply to it. It is a different regime, not a wobble inside one, and the file declares
        # it with '; SPEED_CROSS=' which is CHECKED above against the moves that actually ran.
        _decl_x = re.search(r'^; SPEED_CROSS=([\d.]+)', _rules_txt, re.M)
        if _decl_x and len(_spd) > 1:
            _xv = round(float(_decl_x.group(1)), 1)
            if _xv in _spd and _xv != round(machine.DEFAULT_SPEED, 1):
                print(f"  crossings declared at {_xv:g} mm/s — a second regime, in-air strands "
                      f"rather than deposition onto structure")
                _spd = {k: v for k, v in _spd.items() if k != _xv}
        # A DECLARED BRIDGE SLOWDOWN IS THE SAME ARGUMENT AGAIN, and it is removed here for the same
        # reason the crossing regime is: before the layer-1 test, which keys on there being exactly
        # two speeds left.
        #
        # WHY A BRIDGE MAY SLOW AT ALL, since this file's own comment above argues it should not.
        # Oleg, 2026-08-07: "Yes you can slow down where max flow is limiting factor" and "it is
        # still going to be fast enough to avoid sag". The physics both ways: time in air is what
        # makes a strand sag, so slowing is the wrong direction -- but AT MAX FLOW THE STRAND IS
        # TWICE AS THICK (a 4x rod is 1.001mm against 0.501mm at 1x) and section resists its own
        # weight. Neither settles from first principles, so it is his call, DECLARED, and R3d below
        # proves the declared speeds are the ones actually emitted.
        #
        # ONLY SLOWER, NEVER FASTER. A declared bridge speed above the body speed is not removed, so
        # this cannot become a door for a faster wall wearing a bridge tag.
        if _bspd_decl and len(_spd) > 1:
            _body_now = max(_spd, key=_spd.get)
            _rm = [v for v in _bspd_decl if v in _spd and v < _body_now - 0.6]
            if _rm:
                print(f"  bridges declared at {sorted(_rm)} mm/s — a slowed regime, held at the "
                      f"body's flow ceiling rather than thinned (R3d checks the moves)")
                _spd = {k: v for k, v in _spd.items() if k not in _rm}
        _decl_fl = re.search(r'^; SPEED_FLOOR=([\d.]+)', _rules_txt, re.M)
        if _decl_fl and len(_spd) > 1:
            _flv = round(float(_decl_fl.group(1)), 1)
            if _flv in _spd and _flv < machine.DEFAULT_SPEED - 0.6:
                print(f"  floor declared at {_flv:g} mm/s -- the tall floor bead at the speed "
                      f"that keeps flow constant, a declared regime like layer 1")
                _spd = {k: v for k, v in _spd.items() if k != _flv}
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

    # R3b — THE DECLARED BORE SLOWDOWN MUST ACTUALLY APPEAR IN THE MOVES.
    # Oleg, 2026-07-28: "you are not slowing down on bores - big problem ... 4x slow down rthere."
    # Cutting flow alone left precision low; a '; SPEED_POCKET=' stamp declares a second, slower
    # regime for the pocket arcs, and this verifies the emitted pocket moves run AT it — so the
    # slowdown can never be stamped-but-not-applied, the way the flow guard was five times.
    if _pspd or _pkt_decl is not None:
        _body_sp = max(_spd, key=_spd.get) if _spd else None
        if _pspd and _pkt_decl is None:
            problems.append(f"{sum(_pspd.values())} pocket-precision moves run at {sorted(_pspd)} "
                            f"mm/s but the file declares no '; SPEED_POCKET=' — an undeclared "
                            f"second speed regime. Declare it, or the slowdown is unverifiable.")
        elif _pkt_decl is not None and not _pspd:
            problems.append(f"'; SPEED_POCKET={_pkt_decl:g}' is declared but NO pocket move runs "
                            f"at it — the bore slowdown was stamped and never applied. This is the "
                            f"silent-non-application failure the stamp exists to catch.")
        elif _pspd:
            _pv2 = round(_pkt_decl, 1)
            _wrong = {k: v for k, v in _pspd.items() if abs(k - _pv2) > 0.6}
            if _wrong:
                problems.append(f"pocket moves declared at {_pv2:g} mm/s but {sum(_wrong.values())} "
                                f"run at {sorted(_wrong)} — the declared bore slowdown does not "
                                f"match the emitted speed.")
            elif _body_sp and _pkt_decl > _body_sp - 0.6:
                problems.append(f"'; SPEED_POCKET={_pkt_decl:g}' is not slower than the body speed "
                                f"{_body_sp:g} mm/s — a slowdown that does not slow down. Oleg "
                                f"asked for 4x at the bores.")
            else:
                _ratio = (_body_sp / _pkt_decl) if _body_sp and _pkt_decl else 0
                print(f"  R3b: {sum(_pspd.values())} pocket moves at the declared {_pkt_decl:g} "
                      f"mm/s" + (f" ({_ratio:.1f}x slower than the {_body_sp:g} mm/s body)"
                                 if _ratio else "") + " — bore slowdown applied")

    # R3c — THE DECLARED CORNER SLOWDOWN MUST ACTUALLY APPEAR IN THE MOVES.
    # Oleg, 2026-07-30, after the stand tile's inner concentric-square FLOOR peeled: "the inner
    # square got detachment, on low radius sharp turns you have to slow down." At 50 mm/s the head
    # overshoots a hard corner (Klipper brakes to square_corner_velocity but E meters per mm of
    # PATH, so the bead does not brake with it) and the flung cusp peels. A '; SPEED_CORNER=' stamp
    # declares a slower regime for the sharp-corner ramps, LINK-tagged so R4 skips them; this
    # verifies the emitted corner moves run AT it — the exact mirror of R3b for the pocket, so the
    # slowdown can never be stamped-but-not-applied (the silent-non-application failure).
    if _cspd or _cnr_decl is not None:
        _body_sp = max(_spd, key=_spd.get) if _spd else None
        if _cspd and _cnr_decl is None:
            problems.append(f"{sum(_cspd.values())} corner-slowdown moves run at {sorted(_cspd)} "
                            f"mm/s but the file declares no '; SPEED_CORNER=' — an undeclared "
                            f"second speed regime. Declare it, or the slowdown is unverifiable.")
        elif _cnr_decl is not None and not _cspd:
            problems.append(f"'; SPEED_CORNER={_cnr_decl:g}' is declared but NO corner move runs "
                            f"at it — the corner slowdown was stamped and never applied. This is the "
                            f"silent-non-application failure the stamp exists to catch.")
        elif _cspd:
            _cv2 = round(_cnr_decl, 1)
            _wrong = {k: v for k, v in _cspd.items() if abs(k - _cv2) > 0.6}
            if _wrong:
                problems.append(f"corner moves declared at {_cv2:g} mm/s but {sum(_wrong.values())} "
                                f"run at {sorted(_wrong)} — the declared corner slowdown does not "
                                f"match the emitted speed.")
            elif _body_sp and _cnr_decl > _body_sp - 0.6:
                problems.append(f"'; SPEED_CORNER={_cnr_decl:g}' is not slower than the body speed "
                                f"{_body_sp:g} mm/s — a slowdown that does not slow down. Oleg asked "
                                f"to slow the sharp turns, not match them.")
            else:
                _ratio = (_body_sp / _cnr_decl) if _body_sp and _cnr_decl else 0
                print(f"  R3c: {sum(_cspd.values())} corner moves at the declared {_cnr_decl:g} "
                      f"mm/s" + (f" ({_ratio:.1f}x slower than the {_body_sp:g} mm/s body)"
                                 if _ratio else "") + " — corner slowdown applied")

    # R3d — A DECLARED BRIDGE SLOWDOWN MUST ACTUALLY APPEAR IN THE MOVES, AND AN UNDECLARED ONE
    # MUST FAIL. The exact mirror of R3b and R3c, for the regime added on 2026-08-07.
    #
    # Oleg: "Yes you can slow down where max flow is limiting factor". The generator holds the flow
    # multiplier and drops the feedrate instead of thinning the rod, which is what keeps his line
    # HIERARCHY: at layer 0.48 a 4x accent and an 8x rim both cap to the same 2.79x if you thin
    # them, so "x8 for the final 4 layers" silently stops being distinguishable from the accents.
    #
    # THIS RULE EXISTS BECAUSE THE FILE ABOVE PREDICTED IT. R3's own comment says a bridge stays in
    # the speed histogram on purpose, "If a generator ever slowed one to buy volume, R3 must see it
    # rather than a bridge exemption swallowing it." It did see it, and it failed the file. The
    # answer is a declaration that is CHECKED, never an exemption -- weakening R3 to admit our own
    # feature is the trade this project keeps refusing to make.
    if _bspd_decl is not None or (_bspd and len(_bspd) > 1):
        _body_sp = max(_spd, key=_spd.get) if _spd else None
        _slow = {k: v for k, v in _bspd.items()
                 if _body_sp is not None and k < _body_sp - 0.6}
        if _slow and _bspd_decl is None:
            problems.append(
                f"R3d: {sum(_slow.values())} bridge moves run at {sorted(_slow)} mm/s, below the "
                f"{_body_sp:g} mm/s body, but the file declares no '; SPEED_BRIDGE=' — an "
                f"undeclared second speed regime. A bridge that quietly slows is the exact thing "
                f"R3 keeps bridges in its histogram to catch. Declare it, or the slowdown is "
                f"unverifiable.")
        elif _bspd_decl is not None and not _slow:
            problems.append(
                f"R3d: '; SPEED_BRIDGE={','.join(f'{v:g}' for v in _bspd_decl)}' is declared but NO "
                f"bridge move runs slower than the body speed — the slowdown was stamped and never "
                f"applied. This is the silent-non-application failure the stamp exists to catch.")
        elif _bspd_decl is not None:
            _undeclared = {k: v for k, v in _slow.items()
                           if not any(abs(k - d) < 0.6 for d in _bspd_decl)}
            _unused = [d for d in _bspd_decl
                       if not any(abs(k - d) < 0.6 for k in _bspd.keys())]
            _toofast = [d for d in _bspd_decl if _body_sp is not None and d > _body_sp - 0.6]
            if _undeclared:
                problems.append(
                    f"R3d: {sum(_undeclared.values())} bridge moves run at {sorted(_undeclared)} "
                    f"mm/s, which '; SPEED_BRIDGE=' does not list "
                    f"({','.join(f'{v:g}' for v in _bspd_decl)}) — the emitted speed and the "
                    f"declared one disagree, and the moves are the file.")
            elif _unused:
                problems.append(
                    f"R3d: '; SPEED_BRIDGE=' declares {sorted(_unused)} mm/s and NO bridge move "
                    f"runs at it. A declared regime nobody uses is a stamp describing a file that "
                    f"was not written.")
            elif _toofast:
                problems.append(
                    f"R3d: '; SPEED_BRIDGE=' declares {sorted(_toofast)} mm/s, which is not slower "
                    f"than the {_body_sp:g} mm/s body — a slowdown that does not slow down. This "
                    f"declaration exempts a speed from R3 and must never be a door for a FASTER "
                    f"move wearing a bridge tag.")
            else:
                print(f"  R3d: {sum(_slow.values())} bridge moves at the declared "
                      f"{','.join(f'{v:g}' for v in sorted(_slow))} mm/s "
                      f"({_body_sp/max(_slow):.1f}x to {_body_sp/min(_slow):.1f}x slower than the "
                      f"{_body_sp:g} body) — flow held, speed cut, slowdown applied")

    # R4e — THE BRIDGE FLOW SCHEDULE MUST BE DECLARED, AND EVERY BRIDGE MOVE MUST LAY ONE OF THE
    # DECLARED CROSS-SECTIONS. The exact mirror of R3b/R3c, for the one regime that meters flow UP.
    # Oleg, 2026-08-06: "half the tower number, double the number of layers between solid lines.
    # Double the thickness of solid lines, add 4x line width of new line types every 100 lines plus
    # x8 for the final 4 layers on top of the bucket", and then, asked what the features were:
    # "yes you understand correctly the features are all bridges" / "Just different extrusion
    # volume". So the feature IS a flow schedule, and a flow schedule that is stamped but not
    # applied is the exact failure mode the flow guard hit five times.
    #
    # THREE WAYS IT FAILS, and each one is a real defect rather than a formality:
    #   * bridge moves at a non-body flow with NO stamp -> an undeclared regime; R4 would have to
    #     be blanket-exempted to pass it, which is what this rule exists instead of.
    #   * a stamp with no move at it -> declared and never applied.
    #   * a move whose measured mm2 matches no declared value -> the schedule is not what the file
    #     says it is (e.g. a precedence bug putting an accent where the top rim belongs).
    # MEASURED off the emitted E and the emitted distance, never re-derived from the multiplier.
    #
    # A 1x BRIDGE IS NOT A SECOND REGIME, and this is where an over-strict version of this rule
    # would have become a false claim. Every bucket generated before the flow schedule existed
    # spans its gaps at the body's own bead and stamps '; BRIDGE' on the move; failing those for
    # having no schedule would refuse ~a dozen correct files in out/ and teach the next reader to
    # ignore R4e. So the undeclared branch keys on the move DEVIATING from the file's own bead,
    # measured off the '; bead WxH' header line, using the same 20% band R4 uses.
    _mbb = re.search(r'^; bead ([\d.]+)x([\d.]+)', _rules_txt, re.M)
    _bbead = float(_mbb.group(1)) * float(_mbb.group(2)) if _mbb else None
    _bodd = ([v for v in _bvals if abs(v - _bbead) > 0.20 * _bbead] if (_bvals and _bbead)
             else list(_bvals))
    if _bvals or _bdecl:
        _btol = lambda d: max(0.002, 0.01 * d)
        if _bvals and not _bdecl and _bbead is None:
            problems.append(
                f"R4e REFUSED: {len(_bvals)} '; BRIDGE' move(s) were found, but the file carries "
                f"neither '; BRIDGE_MM2=' nor a parseable '; bead <width>x<height>' stamp. Without "
                f"one of those physical cross-sections R4e cannot decide whether the bridge uses "
                f"the body flow or an undeclared second regime.")
        elif _bvals and not _bdecl and not _bodd:
            print(f"  R4e: {len(_bvals)} '; BRIDGE' move(s), all within 20% of this file's own "
                  f"{_bbead:.4f}mm2 bead — one flow, so there is no schedule to declare.")
        elif _bvals and not _bdecl:
            _rng = f"{min(_bodd):.4f}..{max(_bodd):.4f}"
            problems.append(
                f"R4e: {len(_bodd)} '; BRIDGE' move(s) lay {_rng} mm2/mm against this file's own "
                f"{_bbead:.4f}mm2 bead, but it declares no '; BRIDGE_MM2=' — an undeclared flow "
                f"regime. Declare the schedule, or the multipliers are unverifiable and R4 cannot "
                f"tell them from over-extrusion.")
        elif _bdecl and not _bvals:
            problems.append(
                f"R4e: '; BRIDGE_MM2={','.join(f'{d:g}' for d in _bdecl)}' is declared but NO "
                f"bridge move was found. The schedule was stamped and never applied — the "
                f"silent-non-application failure the stamp exists to catch.")
        else:
            _off = [v for v in _bvals if min(abs(v - d) for d in _bdecl) > _btol(v)]
            _unused = [d for d in _bdecl
                       if not any(abs(v - d) <= _btol(d) for v in _bvals)]
            if _off:
                _w2 = max(_off, key=lambda v: min(abs(v - d) for d in _bdecl))
                problems.append(
                    f"R4e: {len(_off)} bridge move(s) lay a cross-section the file never declared. "
                    f"Worst {_w2:.4f} mm2/mm against declared "
                    f"{','.join(f'{d:.4f}' for d in _bdecl)} — the emitted flow schedule is not "
                    f"the one the header states.")
            elif _unused:
                problems.append(
                    f"R4e: '; BRIDGE_MM2' declares {','.join(f'{d:.4f}' for d in _unused)} mm2/mm "
                    f"but no bridge move lays it. Declared and never applied.")
            else:
                _hist = {}
                for _v in _bvals:
                    _k = min(_bdecl, key=lambda d: abs(_v - d))
                    _hist[_k] = _hist.get(_k, 0) + 1
                print("  R4e: " + ", ".join(
                    f"{_hist[_k]} bridge move(s) at {_k:.4f}mm2/mm" for _k in sorted(_hist))
                    + " — every one matches the declared schedule, and they are exempt from R4 "
                      "BECAUSE they are declared and counted here, not because they are bridges.")
    if _flw and not _decl_flow:
        problems.append("R4 cannot be checked: file carries no '; FLOW=' stamp, so constant flow "
                        "is unverifiable. Regenerate with a current generator.")
    # R7 THE PROBE MUST TOUCH AT PRINT TEMPERATURE.
    # G28 sets Z zero by touching the plate WITH THE NOZZLE, so the nozzle's length at that moment
    # defines the gap for the whole print. A nozzle at 150 C is ~0.046 mm shorter than at 230 over
    # the hotend's length; probe cold and the tip then grows DOWN into the plate, turning a
    # commanded 0.1 mm first layer into ~0.054. That is 46% of the gap, and 1.2 mm2/mm will not go
    # through it -- measured as ZERO adhesion on a bucket and ~10% scrap on a plate of hooks.
    # I introduced that change and could not see it from the file, because the file still said
    # Z0.100 and still metered full flow. Nothing was wrong with the artifact; the machine was
    # being told to measure from the wrong place. So it is checked here.
    _homes = [i for i, _l in enumerate(_lines) if _l.split(';')[0].strip() == 'G28']
    if _homes:
        _hot = None
        for _l in _lines[:_homes[0]]:
            _mt = re.match(r'M10[49] S(\d+)', _l.split(';')[0].strip())
            if _mt:
                _hot = int(_mt.group(1))
        _mp = re.search(r'^; PRINT_TEMP=(\d+)', _rules_txt, re.M)
        _printt = int(_mp.group(1)) if _mp else None
        if _printt is None:
            _after = [int(m.group(1)) for m in
                      (re.match(r'M109 S(\d+)', _l.split(';')[0].strip()) for _l in _lines[_homes[0]:])
                      if m]
            _printt = max(_after) if _after else None
        if _hot is not None and _printt is not None and _hot < _printt - 5:
            problems.append(f"R7 probe temperature: G28 runs with the hotend commanded to {_hot}C "
                            f"but the part prints at {_printt}C. The nozzle is shorter when it "
                            f"probes, so Z zero is recorded high and the tip grows into the plate "
                            f"-- roughly 0.046 mm per 80C, against a {machine.PRESS_HARD:g} mm "
                            f"first layer. Probe at print temperature.")

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
        _qx = _qy = None; _qe = 0.0; _qz = 0.0; _qin = False; _qext = False
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
                    # THE FOURTH FLAG SAYS "THIS POINT CONTINUES THE LAST ONE". Without it the
                    # length below runs the tape measure straight through every inter-part hop:
                    # on the presstest plate that added 1091mm of travel to 420mm of ribbon and
                    # reported a 3.41x fill ratio for a plate whose real figure is 0.9x. The
                    # PRESSED_LAYER1 stamp happened to excuse it, so a wrong number was printed
                    # next to the word "ON PURPOSE" — which is how a real over-fill gets waved
                    # through later.
                    _pl[round(_qz, 2)].append((float(_g2['X']), float(_g2['Y']), _de2, _qext))
            _qext = 'E' in _g2 and 'X' in _g2
            if 'E' in _g2: _qe = float(_g2['E'])
            if 'X' in _g2: _qx = float(_g2['X'])
            if 'Y' in _g2: _qy = float(_g2['Y'])
        _mbw = re.search(r'bead[ =]([\d.]+)', _rules_txt[:4000])
        _bw2 = float(_mbw.group(1)) if _mbw else 2.0
        _fa2 = math.pi * (1.75 / 2) ** 2
        # WHICH LAYER IS WORST IS READ OFF THE FILE, NEVER ASSUMED. The message used to staple
        # "layer 1 over-extrudes ON PURPOSE" onto whichever layer came out worst. On the f022
        # tower coupon that was layer 503 at Z40.26 -- a 1.72x reading 40 mm up a 70 mm tower,
        # handed to the reader as deliberate first-layer behaviour. That is worse than printing
        # no reason at all, because it turns a finding into a reassurance. It read TRUE for the
        # 47 of 76 files in out/ whose worst layer really is layer 1, which is how it survived.
        # Two routes, both off the artifact: the file's own "; ---- layer N of M  z Z" marker
        # when it emits one, else this Z's rank in the emitted ladder. No layer number is typed.
        _z2l = {}
        for _r3 in _rules_txt.splitlines():
            _m3 = re.match(r';\s*----\s*layer\s+(\d+)\s+of\s+\d+\s+z\s+([\d.]+)', _r3.strip())
            if _m3: _z2l[round(float(_m3.group(2)), 2)] = int(_m3.group(1))
        _rank = {_z3: _i3 + 1 for _i3, _z3 in enumerate(sorted(_pl))}
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
            _len2 = 0.0; _gross2 = 0.0; _prev = None; _segs2 = []
            for _rx, _ry, _, _cont in _rows:
                if _prev:
                    _d3 = math.hypot(_rx - _prev[0], _ry - _prev[1])
                    _gross2 += _d3
                    if _cont: _len2 += _d3; _segs2.append(_d3)
                _prev = (_rx, _ry)
            _mm2 = _vol2 / max(_len2, 1e-9)
            _spread = min(max(_mm2 / _h2, _bw2), 40.0)
            _cl2 = max(_spread / 3.0, 0.3); _grid2 = set()
            # int(), not round(): round(1.5)->2 dilated a 2.0mm bead into a 3.33mm footprint,
            # over-stating coverage by 1.67x and under-stating every body layer's fill ratio.
            _k2 = max(0, int(_spread / (2 * _cl2)))
            for _rx, _ry, _, _ in _rows:
                _gx2, _gy2 = int(_rx // _cl2), int(_ry // _cl2)
                for _dx2 in range(-_k2, _k2 + 1):
                    for _dy2 in range(-_k2, _k2 + 1): _grid2.add((_gx2 + _dx2, _gy2 + _dy2))
            _cov2 = len(_grid2) * _cl2 * _cl2
            # IS THIS NUMBER A MEASUREMENT? Asked here so it can never again be answered by the
            # reader assuming it. Three conditions, each read off the grid's own construction --
            # none is a tuned threshold, and each was found by a file in out/ that violates it:
            #   (a) SELF-CONSISTENT. The 3x3 stamp is one deposit wide only while cell ==
            #       spread/3. The 0.3 floor binds whenever spread < 0.9 and breaks that: at the
            #       f022 coupon's 0.43 spread it forces k=0, so every sample marks exactly ONE
            #       cell and "coverage" becomes a count of toolpath samples. Measured there: 210
            #       samples -> 210 distinct cells -> 18.90 mm2, against 30.19 mm2 of real annulus
            #       summed from the six emitted radii. That is the whole of its 1.59x baseline;
            #       the annuli say 1.00x.
            #   (b) NO HOLES. The union of stamps is a footprint only while consecutive stamps
            #       overlap. stand_tile 320x320 emits 400 samples for 52 m of path -- 130 mm
            #       apart against a 2.00 mm stamp -- so coverage reads 1276 mm2 for a 320x320
            #       floor and the ratio reads 81.6x.
            #   (c) LENGTH INTEGRITY. Volume counts every extruding move; length counts only
            #       moves preceded by another extruding move. A bare "G1 F750" corner slowdown
            #       carries no X, so it clears the continuation flag and drops the next segment
            #       from the denominator while its volume stays in the numerator. On
            #       stand_tile 120x120 that reports 7.28 mm2/mm where 10376.93 mm3 over the full
            #       8645 mm of extruding path is 1.20 -- exactly the declared 2.00x0.6 bead.
            # The gap between healthy and broken is ~6x on (c), so 0.95 is a floor, not a knob.
            # WHAT WOULD FALSIFY THIS: subdividing a path without touching geometry or material
            # must not move the ratio. It does -- the f022 coupon walks 1.594 -> 1.277 -> 1.178
            # -> 1.123 at x2/x4/x8. A number that moves when you resample an unchanged curve is
            # measuring the sampling. Fixing that means rasterising coverage ALONG each segment
            # instead of stamping endpoints, which changes every number this guard has ever
            # printed and so needs calibrating against a printed part. Not done here.
            # The reason is carried out to the reader, not left in this comment: a bare "not
            # measured" is the same dead end as a bare "ON PURPOSE" was.
            _stamp2 = (2 * _k2 + 1) * _cl2
            _gap2 = max(_segs2) if _segs2 else 0.0
            _why2 = ""
            if _cl2 > _spread / 3.0 + 1e-9:
                _why2 = (f"the grid cell is floored at {_cl2:.2f}mm for a {_spread:.2f}mm deposit, "
                         f"so it stamps {_stamp2:.2f}mm and every sample lands in its own cell — "
                         f"that counts samples, not footprint")
            elif _gap2 > _stamp2:
                _why2 = (f"samples sit up to {_gap2:.1f}mm apart against a {_stamp2:.2f}mm stamp, "
                         f"so the footprint it unions has holes and coverage is under-counted")
            elif _len2 < 0.95 * max(_gross2, 1e-9):
                _why2 = (f"only {100 * _len2 / max(_gross2, 1e-9):.0f}% of the extruding path "
                         f"counted toward length, so mm2/mm is over-stated about "
                         f"{_gross2 / max(_len2, 1e-9):.1f}x")
            _ratios.append((_zz, _vol2 / max(_cov2 * _h2, 1e-9),
                            _z2l.get(_zz, _rank.get(_zz)), not _why2, _why2))
        _pressed_ok = bool(re.search(r'^; PRESSED_LAYER1=', _rules_txt, re.M))
        if _ratios:
            # THE EXCUSE BELONGS TO THE LAYER IT DESCRIBES, NOT TO THE WHOLE FILE. PRESSED_LAYER1
            # declares that layer 1 is laid into a 0.1 gap on purpose. It was also suppressing the
            # R4b FAILURE at every other layer: 71 of the 76 files here declare it, so the failure
            # branch was unreachable for 93% of them. Layer 1 is dropped from the failure
            # candidates and reported separately; every other layer is judged on its own.
            _l1 = next((_t for _t in _ratios if _t[2] == 1), None)
            _cand = [_t for _t in _ratios if not (_pressed_ok and _t[2] == 1)] or _ratios
            _wz, _wr, _wl, _wmeas, _wwhy = max(_cand, key=lambda t: t[1])
            # "worst layer" stops being true the moment layer 1 is held out of the running, and an
            # imprecise caption is the whole of this bug. So the caption states its own scope.
            _excl = _pressed_ok and _l1 is not None and _wl != 1
            _scope = "worst after the excused layer 1" if _excl else "worst layer"
            _at = f"Z{_wz}" + (f" = layer {_wl}" if _wl is not None
                               else " (no layer index in this file)")
            _tail = ""
            if _excl:
                _tail = (f" Layer 1 reads {_l1[1]:.2f}x and is excused: PRESSED_LAYER1 is "
                         f"declared, so it over-extrudes ON PURPOSE (wide line, welds to plate).")
            if _wr > 1.35 and _wmeas:
                problems.append(f"R4b fill ratio {_wr:.2f}x at {_at} — NOT the deliberate first "
                                f"layer, and nothing in the file declares this layer as "
                                f"over-extruded by design. It deposits {_wr:.2f}x more than its "
                                f"own height can hold over the area it covers. The surplus builds "
                                f"height until the nozzle reaches its own deposit and shears the "
                                f"part off the plate. Overlapping paths need LESS flow than a "
                                f"bead model predicts, not the same.{_tail}")
            elif _wr > 1.35:
                # Over the limit, but the instrument is out of range. Reported as unmeasured
                # rather than dressed up either as a finding or as a pass.
                print(f"  fill ratio {_wr:.2f}x ({_scope}, {_at}) — NOT MEASURED, so NOT "
                      f"judged: {_wwhy}. Neither a pass nor a finding.{_tail}")
            else:
                _note = "" if _wmeas else f", but NOT MEASURED: {_wwhy}"
                print(f"  fill ratio {_wr:.2f}x ({_scope}, {_at}), under the 1.35 limit"
                      f"{_note}.{_tail}")

    if _nlink:
        print(f"  {_nlink} declared LINK move(s) exempt from R4 (contour connectors, metered thin)")
    if _xspd:
        # THE STAMP IS THE CONTRACT. A crossing regime that silently fails to apply is the exact
        # shape of the flow-guard failures this file has been bitten by five times: the file says
        # one thing, the moves do another, and nothing compares them.
        _mx = re.search(r'^; SPEED_CROSS=([\d.]+)', _rules_txt, re.M)
        if not _mx:
            problems.append(f"'; THIN CROSS' moves run at {sorted(_xspd)} mm/s but the file carries "
                            f"no '; SPEED_CROSS=' stamp, so nothing says what they were meant to be")
        else:
            _want = float(_mx.group(1))
            _bad = {v: n for v, n in _xspd.items() if abs(v - _want) > 1e-6}
            if _bad:
                problems.append(f"'; SPEED_CROSS' declares {_want:g} mm/s but {sum(_bad.values())} "
                                f"crossing move(s) run at {sorted(_bad)} — the declared regime is "
                                f"not what the file does")
            else:
                print(f"  crossings run at the declared SPEED_CROSS={_want:g} mm/s "
                      f"({sum(_xspd.values())} moves), a second regime from the body's own speed")
    if _nthin:
        print(f"  {_nthin} declared '; THIN CROSS' move(s) exempt from R4 and STARVED — deliberate "
              f"metered strands across open air, not dry travels. There is no retraction here, so "
              f"the alternative is the SAME ooze uncontrolled.")
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

    # R1  FIRST LAYER MUST BE PRESSED TO THE PLATE.
    # Oleg's rule -- "the nozel need to be 0,1 to board. we need adhesion" -- lived only as the
    # constant machine.PRESS_HARD, which generators were free to ignore. nucleon.py did: it carried
    # its own first_squish=0.85*layer_h model and laid layer 1 at 0.51mm. He caught it on the plate
    # TWICE. A rule that depends on every author remembering it is not a rule, so it is checked
    # here, on the artifact, where no generator can route around it.
    # THE PRIME IS NOT THE FIRST LAYER, AND R1 WAS READING IT AS ONE. The prime sequence descends
    # to Z and lays its line before the body starts, so the first "Z then extrude" pair in the file
    # belongs to the PRIME, not to layer 1. Every generator built on spiraltower's prime shape hit
    # this: 44 files across 12 generators sampled the prime's descent, so their R1 tick was evidence
    # about the purge line and not about the part. Proven on volume_marker — inject Z0.510 as the
    # BODY's layer 1 and R1 stayed green; move the PRIME's Z and R1 fired. The rule was measuring
    # the one line in the file it is not about.
    # AND THEN R1 STILL SKIPPED 151 OF THE 230 FILES IN out/, IN SILENCE. It shared R2's sampler
    # (_zs below), which records a height only when Z lands on a standalone "G1 [F..] Z<z>" line.
    # solid.py, hanger.py and every flowspiral-shaped generator do not write that line: Z rides
    # INSIDE the extruding move ("G1 X.. Y.. Z0.100 E..") or arrives on a "; PRIME-TRAVEL down".
    # For those files _zs stayed empty, "if _zs:" was false, and the rule did not run -- reporting
    # the same green tick a checked file gets, which is the failure the header of this file
    # condemns by name. Proven, not inferred: rewrite all 7703 body Z0.100 in hangerpole to Z0.510
    # -- an entirely unpressed first layer, contradicting that file's own "; PRESSED_LAYER1=0.1"
    # stamp -- and it still printed "passes".
    # Making Z sticky inside _zs would have fixed R1 and BROKEN R2, because _zs is also R2's layer
    # ladder and on a continuous-Z generator the sticky list is not a ladder at all (archtest
    # samples 1.2, 1.2119, 1.2457, 1.2961). So R1 asks its own question here, and _zs below stays
    # exactly the thing R2 has always measured.
    # THE QUESTION R1 ASKS: at what height does the BODY lay its first bead? Z is tracked from
    # every motion line however it arrives -- alone, inside the move, or on a prime travel -- and
    # read at the first extruding move after '; BODY_START'. The body boundary is not optional:
    # 88 of the 230 files lay an UNTAGGED purge line ("G1 F1200 X.. E12", then G92 E0) before the
    # body, so the prime comment alone does not separate purge from part. R3 draws the same
    # boundary for the same reason. Prime-tagged lines are still skipped -- by R4's own test, one
    # definition reused -- because the prime's own bead is not layer 1; but the Z a
    # "; PRIME-TRAVEL down" leaves behind IS the body's Z, so Z is read from those lines even
    # though their extrusion is not.
    # NO BOUNDARY MEANS NO VERDICT, AND THAT IS A FAILURE, NOT A SKIP. A file with no
    # '; BODY_START' cannot be checked, and this file already treats a missing input that way for
    # '; LAYER_H=' and '; MATERIAL=' -- for the reason that is the whole point of this rule: a
    # guard that switches itself off when its input goes missing hands out a tick nobody can tell
    # from a checked one.
    _r1cur, _r1z, _r1body, _r1found = None, None, False, False
    for _l in open(path):
        _c = _l.split(';')[0].strip()
        if _c[:2] in ('G0', 'G1'):
            _mz = re.search(r'\bZ(-?\d+(?:\.\d+)?)', _c)
            if _mz:
                _r1cur = float(_mz.group(1))
        if not _r1body:
            _r1body = 'BODY_START' in _l
            continue
        if 'PRIME' in _l.upper():
            continue
        if _c.startswith('G1') and ' E' in _c and 'X' in _c:
            _r1z, _r1found = _r1cur, True
            break
    if _r1found and _r1z is not None:
        if abs(_r1z - machine.PRESS_HARD) > 1e-6:
            problems.append(f"first layer is at Z{_r1z:.3f} but must be pressed to "
                            f"{machine.PRESS_HARD:.2f} — adhesion comes from the press, and this "
                            f"generator is using its own first-layer model")
    else:
        if not _r1body:
            _why = "the file carries no '; BODY_START' marker"
        elif not _r1found:
            _why = "'; BODY_START' is there but nothing extrudes after it"
        else:
            _why = "no Z is commanded anywhere before the body's first bead"
        problems.append(f"R1 cannot find the body's first bead — {_why}, so nothing in this file "
                        f"says whether layer 1 is pressed to {machine.PRESS_HARD:.2f}")

    # R9  THE FIRST LAYER MAY NOT CHANGE WITHOUT A COUPON.
    # Oleg, 2026-08-06, holding a bucket whose base came off as loose lifted strands: "why you keep
    # messing up base layer every second print?" The answer is structural, not careless.
    # R1 above checks the first layer is pressed, and it reads the COMMANDED Z, which is always
    # 0.100. This machine's Z zero sits 0.15mm HIGH, so a commanded 0.100 with no correction lands
    # at 0.250 -- a gap the bead never touches, which is why three max-bucket starts were cancelled
    # while the width was raised 2.0 -> 3.0 -> 5.0 chasing it. More material cannot fix a gap.
    # The correction is a SET_GCODE_OFFSET line, and until today `grep -c SET_GCODE_OFFSET
    # validate.py` returned ZERO. Every first-layer parameter in this project was being changed
    # behind a gate that examined none of it: a file emitting no offset at all passed exactly as
    # green as a correct one, and two prints were lost to that on 2026-08-06 alone -- the 320mm
    # bucket's five cancels, then the bamboo bucket's base printed as separated strands after --h1
    # was raised to 0.15 and --w1 narrowed to 1.33, starving the weld.
    # WHAT IS CHECKED IS WHERE THE BEAD LANDS, NOT WHAT THE HEADER SAYS. h1 is derived from the
    # emitted offset in force at the body's first bead; w1 from the E and XY of the moves that ran.
    # Header prose has drifted from the emitted moves twice on this project, so the header is
    # cross-examined against the measurement rather than believed.
    # THE ESCAPE HATCH IS EVIDENCE, NOT A FLAG, and it follows this file's own declared-and-counted
    # pattern (';  THIN CROSS' + '; SPEED_CROSS=', which fails when the declared regime is not what
    # the moves do). A '; COUPON=' citation must name a coupon file that EXISTS, must name the
    # numbers THIS file actually lands, and those numbers must appear among the heights that coupon
    # itself printed. A blanket exemption flag would be a way to opt out of the rule, which is what
    # RULES.md says an exception must never be.
    # A MACHINE WITH NO MEASURED ZERR IS NOT JUDGED AND SAYS SO. machine.ZERR has one entry, the
    # K2, because that is the one that was measured. Treating a missing measurement as zero would
    # hand every k1c file a first-layer tick earned by nothing.
    _l1p = re.search(r'^; PRINTER=(\S+)', _rules_txt, re.M)
    _l1machine = _l1p.group(1) if _l1p else None
    _zerr = machine.ZERR.get(_l1machine)
    if _zerr is None:
        print(f"  R9 first layer NOT JUDGED: "
              f"{'this file carries no ; PRINTER= stamp' if _l1machine is None else f'no measured Z-zero error exists for {_l1machine!r}'}"
              f", and machine.ZERR has only {sorted(machine.ZERR)} — so nothing here can say where "
              f"this file's first bead lands. Neither a pass nor a finding.")
    elif not _r1found or _r1z is None:
        print(f"  R9 first layer NOT JUDGED: R1 above already fails for want of a body bead to "
              f"measure. One absence, one verdict.")
    else:
        _fl = first_layer_emitted(path, _zerr)
        _h1, _w1, _zoff = _fl['h1'], _fl['w1'], _fl['zoff']
        _proven = machine.PROVEN_LAYER1.get(_l1machine, [])
        _hit = [p for p in _proven if abs(_h1 - p[0]) <= 0.005 and abs((_w1 or 0) - p[1]) <= 0.05] \
            if _h1 is not None and _w1 is not None else []

        # R1 AND THIS MEASUREMENT CAN DISAGREE ABOUT WHETHER THERE IS A BEAD, and the difference is
        # deliberate: R1 accepts the first move carrying an E, while a WIDTH needs a move that
        # actually deposits over a distance. Rather than crash on the difference -- a validator
        # that raises gives no verdict at all, which is worse than a wrong one -- it is named.
        if _h1 is None:
            print(f"  R9 first layer NOT JUDGED: R1 found a bead at Z{_r1z:.3f} but no body move "
                  f"deposits filament over a measurable distance, so there is no width to compare "
                  f"with anything. Neither a pass nor a finding.")
        # R9a  THE OFFSET MUST BE THERE. This is the specific hole, so it is its own finding with
        # its own arithmetic printed -- "unproven parameters" would be true but would not tell the
        # reader that the file simply never corrects the machine.
        elif _zoff is None:
            problems.append(
                f"R9 no SET_GCODE_OFFSET: this file commands nothing before its first bead, so it "
                f"prints at {_l1machine}'s own Z zero, which sits {_zerr:.3f}mm HIGH. Its layer 1 "
                f"is commanded to Z{_r1z:.3f} and LANDS AT {_h1:.3f}mm — "
                f"{(_h1 / max(_r1z, 1e-9)):.1f}x the gap it meters for, so it deposits "
                f"{(_fl['mm2'] or 0):.4f}mm2/mm as a {(_w1 or 0):.2f}mm strand instead of the "
                f"{(_fl['mm2'] or 0) / max(_r1z, 1e-9):.2f}mm pressed weld its own metering "
                f"assumes. Emit SET_GCODE_OFFSET Z="
                f"{machine.zoff_for(machine.PRESS_HARD, _zerr):.3f} (machine.zoff_for).")
        elif _w1 is None:
            problems.append(f"R9 cannot measure the first layer: the body's first bead is at "
                            f"Z{_r1z:.3f} with offset {_zoff:+.3f}, which lands at {_h1:.3f}mm — "
                            f"at or below the plate. Nothing can be metered into a gap that is not "
                            f"open.")
        else:
            # R9b  THE HEADER MUST AGREE WITH THE MOVES. The '; LAYER1_WIDTH=' stamp names the gap
            # it was metered for; a file whose offset says something else is a file whose author
            # changed one of the two and not the other, which is precisely how --h1 0.15 shipped
            # with a rate meant for 0.10. Both forms of the stamp in out/ carry "the <h> gap".
            # ITS ABSENCE IS NOT A FAILURE, and that is deliberate. Everything R9 judges is
            # measured off the moves, so a file landing the proven weld is proven whether or not
            # its header says so -- failing it for missing prose would be the guard claiming
            # something is impossible when it is only undeclared, which is how a guard earns a
            # reputation for crying wolf and gets switched off. When the weld is NOT proven, R9c
            # below fails on the weld itself, which is the honest finding.
            _mw = re.search(r'^; LAYER1_WIDTH=([\d.]+)mm', _rules_txt, re.M)
            _mg = re.search(r'^; LAYER1_WIDTH=.*?the ([\d.]+) gap', _rules_txt, re.M)
            if not _mw or not _mg:
                print(f"  R9 first layer lands {_h1:.3f}mm x {_w1:.2f}mm wide; the file carries no "
                      f"'; LAYER1_WIDTH=<w>mm ... the <h> gap' stamp, so there is nothing to "
                      f"cross-examine the measurement against.")
            else:
                _dw, _dg = float(_mw.group(1)), float(_mg.group(1))
                if abs(_dg - _h1) > 0.005:
                    # The remedy is only printed when it EXISTS. Above PRESS_HARD+zerr the machine
                    # cannot reach the declared gap at all without raising the commanded Z, and
                    # zoff_for refuses a positive offset rather than hand back a number that lifts
                    # the nozzle off the plate -- so ask it the same question it would refuse only
                    # when the answer is real.
                    _fix = (f"the offset that would land {_dg:.3f} is "
                            f"{machine.zoff_for(_dg, _zerr):+.3f}"
                            if _dg <= machine.PRESS_HARD + _zerr + 1e-9 else
                            f"no offset lands {_dg:.3f} from a commanded Z{_r1z:.3f} — the tallest "
                            f"first layer this machine reaches that way is "
                            f"{machine.PRESS_HARD + _zerr:.3f}")
                    problems.append(
                        f"R9 offset contradicts the file's own declaration: '; LAYER1_WIDTH=' says "
                        f"the bead was metered for a {_dg:.3f}mm gap, but Z{_r1z:.3f} with the "
                        f"emitted SET_GCODE_OFFSET Z={_zoff:+.3f} on a machine {_zerr:.3f} high "
                        f"lands at {_h1:.3f}mm. One of the two was changed without the other; "
                        f"{_fix}.")
                if abs(_dw - _w1) > 0.05:
                    problems.append(
                        f"R9 declared width is not the width laid: the header claims {_dw:.2f}mm "
                        f"landed, the moves deposit {_fl['mm2']:.4f}mm2/mm into a {_h1:.3f}mm gap "
                        f"= {_w1:.2f}mm. The header is prose; this is the file.")

            # R9c  UNPROVEN PARAMETERS NEED A COUPON THAT TESTED THEM.
            if not _hit:
                _ok9, _note9 = layer1_excuse(path, _rules_txt, _h1, _w1, _zerr, _lh)
                if _ok9:
                    print(f"  R9 first layer {_h1:.3f}mm x {_w1:.2f}mm wide — not in "
                          f"{_l1machine}'s proven set, and EXCUSED: {_note9}")
                else:
                    problems.append(
                        f"R9 first layer {_h1:.3f}mm x {_w1:.2f}mm wide is NOT proven on "
                        f"{_l1machine}. What has printed and held: "
                        f"{', '.join(f'{h:.2f}mm x {w:.2f}mm' for h, w in _proven) or 'nothing yet'}"
                        f". {_note9} "
                        f"Print zladder.py, read the plate, then cite the cell it welded on: "
                        f"'; COUPON=<file> h1={_h1:.3f} w1={_w1:.2f} verdict=welded read=<date>'.")
            else:
                print(f"  R9 first layer lands {_h1:.3f}mm x {_w1:.2f}mm wide (Z{_r1z:.3f} + "
                      f"offset {_zoff:+.3f} + {_zerr:.3f} machine error), which is "
                      f"{_l1machine}'s proven weld.")

    # R10  NOTHING MAY EXTRUDE BEFORE THE FIRST BEAD IS PINNED.
    # Oleg, 2026-08-06, with a photograph of a clump of filament hanging off the nozzle and a second
    # of that clump dropped into the middle of a printing plate: "The beginning of extrusion need to
    # be improved generically" / "Also few unacceptable artifacts".
    #
    # WHAT IS REFUSED: any commanded move that advances the extruder while the head does not travel
    # in XY. In this project that is always an opening purge, and it was in 32 generators in seven
    # copy-pasted shapes, dumping 12 to 25mm of filament (28.9 to 60.1 mm3) in one spot.
    #
    # WHY IT IS PHYSICS AND NOT TASTE. The only force that separates molten PLA from a 210C brass
    # face is tension at the far end of the strand, and the only thing that can supply it is a bead
    # already welded to the plate. A stationary purge has no far end: 4 seconds at F300 makes ~96mm
    # of 0.8mm strand whose entire weight is 0.56 mN, against wetted adhesion to hot brass over
    # several mm2. It cannot fall off. It coils onto the tip, and the head carries it into the part.
    #
    # WHY THE RULE IS NOT "ABOVE THE PLATE". Only 17 of the 270 files in out/ purged in free air at
    # Z2; the other 132 purged AT the 0.10 press gap, and this repo had already recorded THAT as the
    # worse failure (presstest.py:168 -- "a 20mm stationary purge (~48mm3) at the 0.1 press gap
    # cannot spread -- it balloons up and COLLARS the nozzle"). Both ends of the Z axis have now
    # been tried and both have been photographed failing, so keying on Z would pass the majority of
    # the defect. The clause is stationary extrusion at ANY Z, and machine.prime() is the third
    # option nobody had tried: move from the first millimetre and let the plate strip the nozzle.
    #
    # PARSING NOTES, each of which is a way this check could have gone blind:
    #   'G1 E20 F300' carries no X and no Y at all, so "did it move" cannot be read off the line --
    #     the last commanded position has to be carried forward and compared.
    #   M82/M83 and 'G92 E' both appear in these files, so the E DELTA has to be tracked and not the
    #     E word. validate.py:988 already records a guard that went blind for the G92 reason.
    #   the purge is usually the FIRST extruding move in the file, so there IS no previous position.
    #     That case is treated as STATIONARY, not as unknown: a machine that has not been told where
    #     it is does not move when it is told only to extrude.
    #   PRIME-tagged lines are NOT exempt here, unlike in R1-R4. The prime is the thing this rule is
    #     about; exempting it would leave the rule with nothing to judge.
    #
    # WHAT THIS RULE DELIBERATELY DOES NOT REFUSE, so that its name stays true to what it measures:
    # a stationary extrusion AFTER material is down. 20-odd solid.py files step Z while extruding at
    # the spiral seam ("G1 F900 Z0.500 E7.57208"), which is XY-stationary but happens with the bead
    # welded to the plate and the previous layer holding the far end -- the strand HAS a far end, so
    # the mechanism this rule is about does not apply. Those are counted and printed, never hidden,
    # because they are a real question; they are just not THIS question, and a rule that refuses
    # them would be refusing 20 files for a reason that is not the defect in the photograph.
    _r10 = []
    _x10 = _y10 = None
    _z10 = 0.0
    _e10 = 0.0
    _abs10 = True
    _pinned10 = False
    for _i, _l in enumerate(open(path), 1):
        _c = _l.split(';')[0].strip()
        if _c.startswith('M82'):
            _abs10 = True
            continue
        if _c.startswith('M83'):
            _abs10 = False
            continue
        if _c.startswith('G92'):
            _m = re.search(r'\bE(-?\d+(?:\.\d+)?)', _c)
            if _m:
                _e10 = float(_m.group(1))
            continue
        if _c[:2] not in ('G0', 'G1'):
            continue
        _mx = re.search(r'\bX(-?\d+(?:\.\d+)?)', _c)
        _my = re.search(r'\bY(-?\d+(?:\.\d+)?)', _c)
        _mz = re.search(r'\bZ(-?\d+(?:\.\d+)?)', _c)
        _nx = float(_mx.group(1)) if _mx else _x10
        _ny = float(_my.group(1)) if _my else _y10
        _nz = float(_mz.group(1)) if _mz else _z10
        _me = re.search(r'\bE(-?\d+(?:\.\d+)?)', _c)
        _d = (math.dist((_x10, _y10), (_nx, _ny))
              if None not in (_x10, _y10, _nx, _ny) else 0.0)
        if _me:
            _v = float(_me.group(1))
            _de = _v - _e10 if _abs10 else _v
            _e10 = _v if _abs10 else _e10 + _v
            if _de > 1e-4:
                if _d < 0.01:
                    _r10.append((_i, _de, _nz, _pinned10))
                else:
                    _pinned10 = True
        _x10, _y10, _z10 = _nx, _ny, _nz
    _unpinned = [r for r in _r10 if not r[3]]
    _seam10 = [r for r in _r10 if r[3]]
    if _unpinned:
        _i0, _de0, _z0, _ = _unpinned[0]
        problems.append(
            f"R10 line {_i0}: {_de0:.2f}mm of filament ({_de0 * machine.A_FIL:.1f} mm3) extruded "
            f"with the head STANDING STILL at Z{_z0:.3f}, before anything has been pinned to the "
            f"plate ({len(_unpinned)} such move(s) in this file). Nothing holds that extrudate, so "
            f"it coils onto the nozzle and rides into the part -- the artifact Oleg photographed on "
            f"2026-08-06. Extrudate must be pinned from the first millimetre it leaves the nozzle: "
            f"call machine.prime(), which moves from the first millimetre at the part's own "
            f"first-layer rate. Files generated before 2026-08-06 fail this legitimately -- "
            f"regenerate them rather than weakening the rule.")
    if _seam10:
        print(f"  R10 {len(_seam10)} stationary extrusion(s) AFTER material is down (first at line "
              f"{_seam10[0][0]}, {_seam10[0][1]:.3f}mm) — not refused: the previous bead holds the "
              f"far end of the strand, which is the mechanism R10 is about. Counted so it is not "
              f"invisible.")

    # R2  NOTHING MAY FLOAT ABOVE THE FIRST LAYER.
    # Oleg's follow-on to the press rule: "play Z smartly we dont want floaring lines". Rebasing
    # layer 1 to 0.1 without rebasing the ladder left a 1.10mm step onto layer 2 -- extruding into
    # air over a 0.60mm bead. Any step bigger than one layer height is a floating line.
    # ONLY Z MOVES THAT ARE FOLLOWED BY EXTRUSION ARE LAYERS. The end-of-print park lift is a Z
    # move too, and on a short part it fell inside the scan window and was reported as a 30.7mm
    # "floating line" -- a false positive that would refuse every 4-layer part.
    # This sampler reads the STANDALONE Z line on purpose. It is the discrete layer ladder, and a
    # generator that moves Z continuously through the extrusion has no ladder for it to measure --
    # feeding it one built from mid-move Z would hand R2 a sampled curve and call the sample rate a
    # layer height. R1 above no longer depends on it.
    _zs, _pend = [], None
    for _l in open(path):
        if 'PRIME' in _l.upper():
            continue
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
        _steps = [round(_zs[i + 1] - _zs[i], 4) for i in range(len(_zs) - 1)]
        # A DECLARED FLOOR HEIGHT is a second ladder rung, not a floating line: '; LAYER_H_FLOOR='
        # (2026-08-08, tall floor beads under 0.24 walls). Steps may reach the larger of the two.
        _mlf = re.search(r'^; LAYER_H_FLOOR=([\d.]+)', _rules_txt, re.M)
        _lmax = max(_lh or 0, float(_mlf.group(1)) if _mlf else 0) or _lh
        _big = [g for g in _steps if _lmax and g > _lmax + 1e-6]
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

    # SHARP-ANGLE CLUSTER — cusps piled at a point don't adhere and peel.
    # Oleg, 2026-07-29, after the bucket base DETACHED: "detachment happened because you created so
    # many sharp angles in the middle - guard should not allow sharp angles". A rose sends every
    # petal to the centre, so hundreds of near-180deg reversals stack at ONE point; the nozzle can
    # not lay a clean bead through a hairpin and the pile-up is a stress concentration that peels.
    # The signal is CLUSTERING, not raw count: distributed sharp turns (raster row-ends, the
    # topper's spring-C mouths) print fine — measured max-cluster <=20 on every part that adhered,
    # vs 360 on the base that detached. So this fails only a dense pile-up (>=50 in one ~45mm patch).
    # XYZ AND E ARE MODAL. The old regex required Z on every extrusion line, so a normal layer
    # that states Z once and then emits XY/E inspected one move and reported green. G3 now carries
    # the machine state and prints its selected-move count on every body file.
    _g3 = sharp_angle_coverage(_lines)
    if not _g3['moves_examined']:
        problems.append("G3 sharp-angle rule REFUSED: zero real body extrusion moves examined")
    elif _g3['max_cluster'] >= 50:
            problems.append(f"SHARP-ANGLE CLUSTER: {_g3['max_cluster']} near-reversals (>140deg) pile into one "
                            f"~45mm patch — cusps concentrate stress and do not adhere (Oleg: the "
                            f"base detached from 'so many sharp angles in the middle'). Spread the "
                            f"convergence out; do not run many paths into a single point.")
    else:
        print(f"  G3 examined {_g3['moves_examined']} real extrusion moves; sharp-angle cluster "
              f"max {_g3['max_cluster']} (>140deg reversals in any ~45mm patch; fails at 50) — "
              f"{_g3['sharp_turns']} sharp turns total, distributed")

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
