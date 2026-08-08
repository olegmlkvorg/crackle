#!/usr/bin/env python3
"""qa_weld — physically simulate the floor and MEASURE how well the bottom is attached to the
walls, off the EMITTED gcode. Oleg, 2026-08-08: "the net and the outer wall line do not have
sufficient connection points" and "you need to physically simulate and check how well bottom
attached to walls".

WHAT IT SIMULATES. Every extruded floor move becomes a 2D capsule (stadium): centreline = the
move, width = the material it actually carries (dE * A_FIL / length / layer gap) -- read off the
file, never off the flags. Two capsules are WELDED only when their beads OVERLAP by at least
MARGIN. Edge-to-edge contact at zero margin is NOT a weld: the commanded butt is exactly what the
v15 plate showed coming apart, because beads land narrower than commanded (the same physics behind
FLOOR1_OVERLAP=0.8 in bucket_towers.py -- the only floor that has ever welded overlaps by a fifth
of a bead, and that margin is what a zero-margin butt spends).

THREE VERDICTS PER FLOOR LAYER, each measurable and each proven able to fire on v15:
  ATTACH   walk the border (post wall arcs + rim chords) in 0.5mm steps; a step is HELD when some
           fill/raster capsule overlaps the border bead by >= MARGIN. The longest unheld run is
           judged against --max-run (default: the file's own --floor-pitch, because the border
           must not be weaker than the lattice welds to ITSELF). Layer 1 is REPORTED, not judged:
           it is the plate weld, its raster laps the rim by construction, and its evidence is the
           coupon.
  ONE BODY connectivity, union-find over weld contacts: wall, rim, fill and raster must be ONE
           component. This is the literal form of "attached": a fill ring welded to the wall but
           only butted to the raster leaves the bottom holding the walls with nothing.
  NO PILE  no spot may carry more than 2.7 bead-heights of MATERIAL DEPTH (elliptical bead
           sections summed per 0.4mm cell). Butt's twin failure: separate passes piling onto one
           centreline -- what the retired ring clamp would have printed (every sagging ring
           projected onto ONE circle; on layer 1 that circle sits OUTSIDE the rim polygon), had
           the branch bug not kept the rings from the emitter entirely. Three near-coincident
           beads fail; the designed 0.2-bead laps pass. THE SEAM CORRIDOR IS EXEMPT, DECLARED
           AND COUNTED: every floor layer's entry/exit plumbing (raster-to-ring link, comb
           closure, the exit rib) converges in one <1 deg radial corridor at the seam by
           construction -- it measures ~3.2 bead-heights, it is one strip per layer, and every
           printed floor has carried it. Piles there are REPORTED with their depth; anywhere
           else they FAIL. --seam-exempt-deg 0 removes the exemption (how this check is proven
           able to fire: v16 reads 7 spots at the seam with it off). Judged above the plate
           weld, like ATTACH: layer 1's 1.25x pressed sheet is declared design.

GEOMETRY comes from the file's own '; CMD=' line (the verbatim invocation every plate carries),
re-derived with the generator's own arithmetic. If the re-derivation does not find the walls in
the emitted moves, the tool DECLINES (exit 2) rather than approving what it could not measure.

Usage: python3 tools/qa_weld.py out/bucket_towers_*.gcode [--max-run MM] [--margin MM]
Exit: 0 all floor layers pass, 1 a gate fired, 2 cannot measure.
"""
import argparse, math, os, re, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine

A_FIL = machine.A_FIL
MARGIN = 0.05          # mm of bead overlap below which a joint is a butt, not a weld
STEP = 0.5             # border walk step, mm


def parse_art(path):
    """art_bucket.py stamps its SOLVED geometry (per-post centre + mouth azimuth for both
    rings, the exit rib, the cut outline) because it cannot be cheaply re-derived: the posts
    come from a PNG trace plus a per-post mouth solve. WHAT THIS COSTS, honestly: the circle
    branch re-derives its border from CMD flags by independent arithmetic; this branch takes
    the border AS STAMPED, so a wrong stamp is caught only by the existing DECLINE (no wall
    arcs found where the stamps claim them), not by a second derivation."""
    posts, wrap, tower_d, exit_seg, hole = [], None, None, None, []
    for ln in open(path):
        if ln.startswith('; ART_POST '):
            t = ln.split()
            posts.append((t[2], int(t[3]), float(t[4]), float(t[5]),
                          math.radians(float(t[6].split('=')[1]))))
        elif ln.startswith('; ART_WRAP='):
            m = re.search(r'ART_WRAP=([\d.]+) TOWER_D=([\d.]+)', ln)
            wrap, tower_d = float(m.group(1)), float(m.group(2))
        elif ln.startswith('; ART_EXIT '):
            t = ln.split()
            exit_seg = ((float(t[2]), float(t[3])), (float(t[4]), float(t[5])))
        elif ln.startswith('; ART_HOLE '):
            for tok in ln.split()[2:]:
                if ',' in tok:
                    x, _, y = tok.partition(',')
                    try:
                        hole.append((float(x), float(y)))
                    except ValueError:
                        break
        elif 'BODY_START' in ln:
            break
    if not posts or wrap is None:
        return None
    return dict(posts=posts, wrap=wrap, tower_d=tower_d, exit_seg=exit_seg, hole=hole)


def geometry_art(cmd, art):
    """The two-ring border, from the emitter's stamps (see parse_art for what that trades)."""
    bw = machine.SLICER_LINE_W
    r_t = (art['tower_d'] - bw) / 2.0
    half = math.radians(art['wrap'] / 2.0)
    toff = math.radians((360.0 - art['wrap']) / 2.0)
    rings = {}
    for ring, k, x, y, mu in art['posts']:
        rings.setdefault(ring, []).append((k, (x, y), mu))
    cs, mus, chords = [], [], []
    for ring in ('outer', 'inner'):
        ps = sorted(rings.get(ring, []))
        for k, c, mu in ps:
            cs.append(c)
            mus.append(mu)
        nn = len(ps)
        for k in range(nn):
            _, c1, m1 = ps[k]
            _, c2, m2 = ps[(k + 1) % nn]
            lead = (c1[0] + r_t * math.cos(m1 + toff), c1[1] + r_t * math.sin(m1 + toff))
            trail = (c2[0] + r_t * math.cos(m2 - toff), c2[1] + r_t * math.sin(m2 - toff))
            chords.append((lead, trail))
    printer = cmd.get('printer', machine.DEFAULT_PRINTER)
    bedx, bedy = machine.BED[printer]
    return dict(mode='art', bw=bw, cx=bedx / 2.0, cy=bedy / 2.0, n=len(cs), cs=cs, phis=mus,
                r_t=r_t, half=half, toff=toff, wdir=1, chords=chords, r_h=None,
                seam_th=None, exit_seg=art['exit_seg'], hole=art['hole'],
                w1=float(cmd.get('w1', 0)) or None, h1=float(cmd.get('h1', 0)) or None,
                lh_f=float(cmd.get('floor_layer_h', 0)) or float(cmd.get('layer_h', 0.24)),
                floor_pitch=float(cmd.get('net_pitch', 4.0)))


def _in_poly(pt, poly):
    """Point-in-polygon, even-odd."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (x2 - x1) * (y - y1) / (y2 - y1):
            inside = not inside
    return inside


def border_path_art(g):
    """Border samples for the two-ring part: every post's MATERIAL arc + every chord.
    Steps INSIDE the cut outline are EXEMPT-BY-DESIGN and marked: the hole-facing side of an
    inner post's arc faces a void, and nothing can ever lap a void's side. Returns
    [(pt, exempt)]."""
    pts = []
    for c, mu in zip(g['cs'], g['phis']):
        a0 = mu - g['toff']
        sweep = -2.0 * g['half']
        steps = max(2, int(abs(sweep) * g['r_t'] / STEP))
        for t in range(steps + 1):
            a = a0 + sweep * t / steps
            p = (c[0] + g['r_t'] * math.cos(a), c[1] + g['r_t'] * math.sin(a))
            pts.append((p, bool(g['hole']) and _in_poly(p, g['hole'])))
    for a, b in g['chords']:
        m = max(1, int(math.dist(a, b) / STEP))
        for t in range(m + 1):
            p = (a[0] + (b[0] - a[0]) * t / m, a[1] + (b[1] - a[1]) * t / m)
            pts.append((p, bool(g['hole']) and _in_poly(p, g['hole'])))
    return pts


def parse_cmd(path):
    """The generator's own invocation, from the '; CMD=' stamp. Returns {flag: value}."""
    for ln in open(path):
        if ln.startswith('; CMD='):
            toks = shlex.split(ln[7:].strip())
            out = {'_gen': toks[0] if toks else ''}
            i = 1
            while i < len(toks):
                if toks[i].startswith('--'):
                    k = toks[i][2:].replace('-', '_')
                    if i + 1 < len(toks) and not toks[i + 1].startswith('--'):
                        out[k] = toks[i + 1]
                        i += 2
                    else:
                        out[k] = True
                        i += 1
                else:
                    i += 1
            return out
        if 'BODY_START' in ln:
            break
    return None


def geometry(cmd, stag_deg):
    """The border, re-derived with bucket_towers' own arithmetic from the CMD flags."""
    bw = machine.SLICER_LINE_W
    dia = float(cmd.get('dia', 100.0))
    pitch = float(cmd.get('pitch', 25.0))
    stick = float(cmd.get('stick_d', 3.175))
    allow = float(cmd.get('bore_allow', 1.225))
    wrap = float(cmd.get('wrap_deg', 250.0))
    mouth = cmd.get('mouth', 'in')
    printer = cmd.get('printer', machine.DEFAULT_PRINTER)
    tower_d = float(cmd['tower_d']) if 'tower_d' in cmd else stick + allow + 2.0 * bw
    r_ring = dia / 2.0
    r_t = (tower_d - bw) / 2.0
    n = max(3, int(math.ceil(2 * math.pi * r_ring / pitch)))
    bedx, bedy = machine.BED[printer]
    cx, cy = bedx / 2.0, bedy / 2.0
    phis = [2 * math.pi * k / n for k in range(n)]
    cs = [(cx + r_ring * math.cos(p), cy + r_ring * math.sin(p)) for p in phis]
    wdir = -1 if mouth == 'out' else 1
    half = math.radians(wrap / 2.0)
    stag = math.radians(stag_deg)
    sp = lambda k, off: (cs[k][0] + r_t * math.cos(phis[k] + off),
                         cs[k][1] + r_t * math.sin(phis[k] + off))
    starts = [sp(k, stag - wdir * half) for k in range(n)]
    ends = [sp(k, stag + wdir * half) for k in range(n)]
    chords = [(ends[k], starts[(k + 1) % n]) for k in range(n)]
    r_poly = min(math.hypot(a[0] + (b[0] - a[0]) * t / 64 - cx,
                            a[1] + (b[1] - a[1]) * t / 64 - cy)
                 for a, b in chords for t in range(65))
    r_h = min(r_poly, r_ring - r_t) - 2.0 * bw
    seam_th = math.atan2(starts[0][1] - cy, starts[0][0] - cx)
    return dict(bw=bw, cx=cx, cy=cy, n=n, cs=cs, phis=phis, r_t=r_t, r_ring=r_ring,
                stag=stag, half=half, wdir=wdir, chords=chords, r_poly=r_poly, r_h=r_h,
                seam_th=seam_th,
                w1=float(cmd.get('w1', 0)) or None, h1=float(cmd.get('h1', 0)) or None,
                lh_f=float(cmd.get('floor_layer_h', 0)) or float(cmd.get('layer_h', 0.24)),
                floor_pitch=float(cmd.get('floor_pitch', 2.5)))


def seg_dist(p, q, a, b):
    """Min distance between segments p-q and a-b (2D)."""
    def pt(s, u, v):
        dx, dy = v[0] - u[0], v[1] - u[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-18:
            return math.dist(s, u)
        t = max(0.0, min(1.0, ((s[0] - u[0]) * dx + (s[1] - u[1]) * dy) / l2))
        return math.hypot(s[0] - u[0] - dx * t, s[1] - u[1] - dy * t)
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    # proper intersection = distance 0
    d1, d2 = cross(a, b, p), cross(a, b, q)
    d3, d4 = cross(p, q, a), cross(p, q, b)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(pt(p, a, b), pt(q, a, b), pt(a, p, q), pt(b, p, q))


def floor_layers(path, g):
    """[(label, z, gap_mm, [(p, q, w, idx)])] for every '(floor latch' layer, widths MEASURED."""
    layers = []
    cur = None
    x = y = None
    e = 0.0
    z = 0.0
    for ln in open(path):
        if ln.startswith('; ---- layer'):
            if cur and cur[3]:
                layers.append(cur)
            cur = None
            m = re.match(r'; ---- layer (\d+) of \d+\s+z ([\d.]+)\s+\(floor latch', ln)
            if m:
                li = len(layers)
                gap = (g['h1'] or machine.PRESS_HARD) if li == 0 else g['lh_f']
                cur = (f"layer {m.group(1)}", float(m.group(2)), gap, [])
        c = ln.split(';')[0].strip()
        if not c.startswith(('G0', 'G1')):
            if c.startswith('G92'):
                m = re.search(r'E(-?[\d.]+)', c)
                if m:
                    e = float(m.group(1))
            continue
        gd = dict(re.findall(r'\b([XYZE])(-?\d+(?:\.\d+)?)', c))
        nx = float(gd['X']) if 'X' in gd else x
        ny = float(gd['Y']) if 'Y' in gd else y
        if 'Z' in gd:
            z = float(gd['Z'])
        de = 0.0
        if 'E' in gd:
            v = float(gd['E'])
            de, e = v - e, v
        if cur is not None and de > 0 and None not in (x, y, nx, ny):
            d = math.hypot(nx - x, ny - y)
            if d > 1e-6:
                w = de * A_FIL / d / cur[2]
                cur[3].append(((x, y), (nx, ny), w, len(cur[3])))
        if 'X' in gd:
            x = nx
        if 'Y' in gd:
            y = ny
    if cur and cur[3]:
        layers.append(cur)
    return layers


def classify(segs, g):
    """WALL / RIM / RASTER / FILL per segment, purely geometric. Art parts have no central
    raster disc (r_h is None): everything not wall/rim is FILL, and ATTACH tests both."""
    bw, r_t, r_h = g['bw'], g['r_t'], g['r_h']
    cx, cy = g['cx'], g['cy']
    out = []
    for (p, q, w, i) in segs:
        cls = None
        for c in g['cs']:
            if (abs(math.dist(p, c) - r_t) < 0.45 * bw
                    and abs(math.dist(q, c) - r_t) < 0.45 * bw):
                cls = 'WALL'
                break
        if cls is None and r_h is not None:
            rp = math.hypot(p[0] - cx, p[1] - cy)
            rq = math.hypot(q[0] - cx, q[1] - cy)
            if max(rp, rq) <= r_h + 0.55 * w:
                cls = 'RASTER'
        if cls is None:
            for a, b in g['chords']:
                if seg_dist(p, q, a, b) < 0.45 * w:
                    cls = 'RIM'
                    break
        out.append((p, q, w, i, cls or 'FILL'))
    return out


def hash_segs(segs, cell=2.0):
    grid = {}
    for s in segs:
        (p, q) = s[0], s[1]
        x0, x1 = sorted((p[0], q[0]))
        y0, y1 = sorted((p[1], q[1]))
        r = s[2] / 2.0 + 0.5
        for gx in range(int((x0 - r) // cell), int((x1 + r) // cell) + 1):
            for gy in range(int((y0 - r) // cell), int((y1 + r) // cell) + 1):
                grid.setdefault((gx, gy), []).append(s)
    return grid, cell


def near(grid, cell, p, q, w):
    x0, x1 = sorted((p[0], q[0]))
    y0, y1 = sorted((p[1], q[1]))
    r = w / 2.0 + 0.5
    seen, out = set(), []
    for gx in range(int((x0 - r) // cell), int((x1 + r) // cell) + 1):
        for gy in range(int((y0 - r) // cell), int((y1 + r) // cell) + 1):
            for s in grid.get((gx, gy), ()):
                if s[3] not in seen:
                    seen.add(s[3])
                    out.append(s)
    return out


def border_path(g):
    """Sampled border: post wall arcs (material sector) + rim chords, in walk order."""
    pts = []
    n = g['n']
    for k in range(n):
        c, phi = g['cs'][k], g['phis'][k]
        a0 = phi + g['stag'] - g['wdir'] * g['half']
        sweep = g['wdir'] * 2.0 * g['half']
        steps = max(2, int(abs(sweep) * g['r_t'] / STEP))
        for t in range(steps + 1):
            a = a0 + sweep * t / steps
            pts.append((c[0] + g['r_t'] * math.cos(a), c[1] + g['r_t'] * math.sin(a)))
        a, b = g['chords'][k]
        m = max(1, int(math.dist(a, b) / STEP))
        for t in range(1, m + 1):
            pts.append((a[0] + (b[0] - a[0]) * t / m, a[1] + (b[1] - a[1]) * t / m))
    return pts


def check(path, max_run_flag=None, margin=MARGIN, seam_deg=1.5):
    cmd = parse_cmd(path)
    if not cmd:
        print(f"{path}\n  DECLINE: no '; CMD=' stamp -- geometry cannot be re-derived, so "
              f"attachment cannot be measured. Neither a pass nor a finding.")
        return 2
    art = parse_art(path) if 'art_bucket' in cmd.get('_gen', '') else None
    if 'art_bucket' in cmd.get('_gen', '') and not art:
        print(f"{path}\n  DECLINE: an art_bucket file with no ART_POST stamps; the border "
              f"cannot be placed.")
        return 2
    if art:
        g = geometry_art(cmd, art)
        border_x = border_path_art(g)
    else:
        m = None
        for ln in open(path):
            m = m or re.search(r'rotated ([\d.]+) deg', ln)
            if 'BODY_START' in ln:
                break
        if not m:
            print(f"{path}\n  DECLINE: no stagger stamp; the border cannot be placed.")
            return 2
        g = geometry(cmd, float(m.group(1)))
        border_x = [(p, False) for p in border_path(g)]
    layers = floor_layers(path, g)
    if not layers:
        print(f"{path}\n  DECLINE: no '(floor latch' layers -- nothing here is a floor.")
        return 2
    max_run = max_run_flag if max_run_flag is not None else g['floor_pitch']
    border = [p for p, _ in border_x]
    n_bexempt = sum(1 for _, e in border_x if e)
    print(f"{path}")
    if art:
        print(f"  geometry: {g['n']} posts (two rings) r_t {g['r_t']:.2f}, from ART_POST "
              f"stamps CROSS-CHECKED against the emitted arcs (a wrong stamp DECLINES); weld "
              f"margin {margin:g}mm, border run limit {max_run:g}mm (= --net-pitch); "
              f"{n_bexempt} border steps inside the cut are exempt-by-design (a void's side "
              f"cannot be lapped)")
    else:
        print(f"  geometry: {g['n']} posts r_t {g['r_t']:.2f} on {2*g['r_ring']:g}mm, "
              f"r_poly {g['r_poly']:.2f}, raster disc r_h {g['r_h']:.2f}; weld margin "
              f"{margin:g}mm, border run limit {max_run:g}mm (= --floor-pitch: the border must "
              f"not be weaker than the lattice welds to itself)")
    fails = 0
    for li, (label, z, gap, raw) in enumerate(layers):
        segs = classify(raw, g)
        if not any(s[4] == 'WALL' for s in segs):
            print(f"  {label}: DECLINE -- re-derived geometry finds NO wall arcs in the emitted "
                  f"moves; the frame is wrong and nothing below could be trusted.")
            return 2
        grid, cell = hash_segs(segs)
        bead = sorted(s[2] for s in segs)[len(segs) // 2]

        # ONE BODY -- union-find over capsule overlaps >= margin.
        parent = list(range(len(segs)))
        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for s in segs:
            for o in near(grid, cell, s[0], s[1], s[2]):
                if o[3] <= s[3]:
                    continue
                if abs(o[3] - s[3]) <= 2:      # path neighbours share an endpoint by construction
                    ra, rb = find(s[3]), find(o[3])
                    if ra != rb:
                        parent[ra] = rb
                    continue
                d = seg_dist(s[0], s[1], o[0], o[1])
                if d <= (s[2] + o[2]) / 2.0 - margin:
                    ra, rb = find(s[3]), find(o[3])
                    if ra != rb:
                        parent[ra] = rb
        comps = {}
        for s in segs:
            comps.setdefault(find(s[3]), []).append(s[4])
        big = max(comps.values(), key=len)
        loose = {c: sorted(set(v)) for c, v in comps.items()
                 if v is not big and len(v) > 3}    # <=3 segs = a stub, reported via runs anyway
        one_body = not loose

        # ATTACH -- the border walk. Exempt steps (the cut-facing side of an inner-ring arc,
        # art parts only) neither hold nor extend a run: nothing can lap a void's side.
        held = []
        for bp, ex in border_x:
            if ex:
                held.append(None)
                continue
            ok = False
            for o in near(grid, cell, bp, bp, bead):
                if o[4] in ('FILL', 'RASTER'):
                    d = seg_dist(bp, bp, o[0], o[1])
                    if d <= (bead + o[2]) / 2.0 - margin:
                        ok = True
                        break
            held.append(ok)
        runs, cur_run, worst = [], 0.0, 0.0
        for h in held + [True]:
            if h is False:
                cur_run += STEP
            else:
                if cur_run:
                    runs.append(cur_run)
                worst = max(worst, cur_run)
                cur_run = 0.0
        _judged = [h for h in held if h is not None]
        weld_frac = (sum(_judged) / len(_judged)) if _judged else 1.0

        # NO PILE -- DEPTH per 0.4mm cell, in bead heights. Two instruments were tried and
        # retired here, each for measuring the wrong quantity: whole-cell dilation inflated a
        # 0.82mm bead to a 1.2mm stamp (4788 phantom piles = designed lap NEIGHBOURS), and a
        # pass COUNT read a bead-EDGE graze as a full stack (266 phantoms = the unavoidable
        # triple corners of a lap lattice, where three beads' thin edges share one point). The
        # quantity that ruins a plate is MATERIAL DEPTH over a spot, so that is what is summed:
        # each pass contributes an elliptical cross-section, sqrt(1-(2d/w)^2) bead-heights at
        # distance d from its centreline -- full height on the centreline, ~0 at the edge.
        # PILE_DEPTH fires above 2.7: three near-coincident centrelines (v15's rim stack ran
        # SEVEN) fail; two stacked beads plus an edge graze -- the floor's own exit rib riding
        # the band, the deepest thing the design commits -- pass at ~2.5.
        pc = 0.4
        cells = {}
        for (p, q, w, i, cls) in segs:
            x0, x1 = sorted((p[0], q[0]))
            y0, y1 = sorted((p[1], q[1]))
            r = w / 2.0
            for gx in range(int((x0 - r) / pc), int((x1 + r) / pc) + 2):
                for gy in range(int((y0 - r) / pc), int((y1 + r) / pc) + 2):
                    ctr = ((gx + .5) * pc, (gy + .5) * pc)
                    d = seg_dist(ctr, ctr, p, q)
                    if d > r:
                        continue
                    dep = math.sqrt(max(0.0, 1.0 - (2.0 * d / w) ** 2))
                    lst = cells.setdefault((gx, gy), [])
                    if lst and i - lst[-1][0] <= 3:      # same bead continuing: deepest sample
                        lst[-1][0] = i                   # wins, never summed with itself
                        lst[-1][1] = max(lst[-1][1], dep)
                    else:
                        lst.append([i, dep])
        PILE_DEPTH = 2.7
        piles, seam_piles = {}, {}
        for k2, v in cells.items():
            tot = sum(c for _, c in v)
            if tot > PILE_DEPTH:
                ctr = ((k2[0] + .5) * pc, (k2[1] + .5) * pc)
                if g.get('seam_th') is not None:
                    # circle parts: the angular seam corridor (entry/exit plumbing at theta 0)
                    th_abs = math.atan2(ctr[1] - g['cy'], ctr[0] - g['cx'])
                    lo = min(0.0, g['seam_th']) - math.radians(seam_deg)
                    hi = max(0.0, g['seam_th']) + math.radians(seam_deg)
                    exempt_here = seam_deg > 0 and lo <= th_abs <= hi
                else:
                    # art parts: the EXIT RIB corridor -- one declared radial strip per layer,
                    # same jurisdiction as the circle seam. --seam-exempt-deg 0 disables it.
                    exempt_here = (seam_deg > 0 and g.get('exit_seg')
                                   and seg_dist(ctr, ctr, *g['exit_seg']) <= 1.5)
                if exempt_here:
                    seam_piles[k2] = tot
                else:
                    piles[k2] = tot
        worst_pile = max(piles.values()) if piles else 0.0

        verdicts = []
        judged_run = li > 0                    # layer 1's border runs: reported, not judged
        if not one_body:
            verdicts.append(f"FAIL ONE-BODY: {len(loose)} loose island(s) "
                            f"{sorted(set(tuple(v) for v in loose.values()))} not welded to the "
                            f"main body at {margin:g}mm margin")
        if judged_run and worst > max_run:
            verdicts.append(f"FAIL ATTACH: {worst:.1f}mm of border has no fill welded to it "
                            f"(limit {max_run:g})")
        # PILE shares ATTACH's jurisdiction: layer 1 is the declared pressed sheet, whose 1.25x
        # coverage (raster laps, turnaround convergences) IS the design the R4b PRESSED_LAYER1
        # excuse already owns -- judging it here would re-refuse a proven weld. Reported, always.
        if judged_run and piles:
            verdicts.append(f"FAIL PILE: {len(piles)} spot(s) exceed {PILE_DEPTH:g} bead-heights "
                            f"of material (worst {worst_pile:.1f})")
        status = "; ".join(verdicts) if verdicts else "PASS"
        print(f"  {label} z{z:g} gap {gap:g}: {len(segs)} beads (median {bead:.2f}mm), "
              f"border welded {weld_frac*100:.0f}%, longest unwelded run {worst:.1f}mm"
              f"{' (REPORTED, not judged: plate-weld layer)' if not judged_run else ''}, "
              f"components {len(comps)}, piled spots {len(piles)}"
              + (f" + {len(seam_piles)} in the seam corridor (worst "
                 f"{max(seam_piles.values()):.1f} bead-heights: the entry/exit plumbing, one "
                 f"strip per layer by design)" if seam_piles else "")
              + f" -> {status}")
        if verdicts:
            fails += 1
    print(f"  {'FAIL' if fails else 'PASS'}: bottom-to-wall attachment, "
          f"{len(layers) - fails}/{len(layers)} floor layers clean")
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('gcode', nargs='+')
    ap.add_argument('--max-run', type=float, default=None)
    ap.add_argument('--margin', type=float, default=MARGIN)
    ap.add_argument('--seam-exempt-deg', type=float, default=1.5)
    args = ap.parse_args()
    rc = 0
    for f in args.gcode:
        rc = max(rc, check(f, args.max_run, args.margin, args.seam_exempt_deg))
    sys.exit(rc)
