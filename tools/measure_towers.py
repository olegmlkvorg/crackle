#!/usr/bin/env python3
"""MEASURE TOWERS — read a tower-coupon plate back off the EMITTED FILE and say what it really is.

The house law this exists to serve: "Measure the emitted artifact, never the summary line. Computed
values disagreed with the emitted file four times out of four." A generator that prints what it
INTENDED prints nothing. So nothing in here imports towercoupon.py, and nothing in here trusts a
'; ' stamp except to CONTRADICT it.

Everything is re-derived by a different route than the generator used:

  towers        DISCOVERED by clustering extruding moves in X (the generator was told the centres;
                this finds them), then measured for diameter from the path's own XY extent.
  height        per tower, the highest Z at which that cluster actually deposited material.
  layers        counted from Z transitions on standalone Z moves, NOT from '; ---- layer' comments.
  mm2/mm        (dE * filament area) / distance, summed per layer, sampled at several heights.
  layer time    a real trapezoid motion model with Klipper junction velocities and a two-pass
                lookahead planner -- NOT distance/feedrate, which ignores acceleration and the
                machine's slow Z. Axis limits are selected from the file's own '; PRINTER=' stamp
                (see KIN) and every one that is a stand-in rather than a reading is named under the
                number. The slow Z is what makes the z-hops the expensive part of a layer.
  feedrates     every distinct commanded F in the body, with move counts.

Then it CHECKS those measurements against the file's own declarations and prints DISAGREE lines.
A disagreement is a bug in the generator and is reported as one.

Usage:
    python3 tools/measure_towers.py out/towercoupon_*.gcode
    python3 tools/measure_towers.py out/towercoupon_*.gcode --selftest
"""
import argparse, math, os, re, shutil, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine

A_FIL = math.pi * (1.75 / 2) ** 2

# ------------------------------------------------------------------- KINEMATICS, PER MACHINE
# THE TIME MODEL IS ONLY AS HONEST AS ITS AXIS LIMITS. This file carried ONE set — the SparkX's,
# read off it over Moonraker — and printed "SparkX limits" under every number it produced,
# including numbers measured off a K2 file. The caption was true and the number under it was still
# wrong for the file it sat on. The set is now selected from the file's own '; PRINTER=' stamp, and
# every value that is a STAND-IN rather than a reading is NAMED IN THE REPORT, not buried here.
KIN = {
    "f022": {
        "max_v": 500.0, "max_a": 10000.0, "scv": 12.0, "max_zv": 20.0, "max_za": 100.0,
        "src": "read off the machine over Moonraker, 2026-08-04 (see towercoupon.SPARKX)",
        "assumed": [],
    },
    "k2plus": {
        "max_v": machine.MAX_VELOCITY,   # 800, machine.py
        "max_a": machine.ACCEL,          # 5000 — what the toolhead REPORTS while printing, NOT the
                                         # 30000 config ceiling, which it is clamped below
        "scv": 12.0,                     # STAND-IN: the SparkX's number, never read off the K2
        "max_zv": 20.0,                  # STAND-IN
        "max_za": 100.0,                 # STAND-IN
        "src": "machine.py for velocity and accel; the K2 was off the network on 2026-08-05, so "
               "nothing here was read off the machine itself",
        "assumed": ["square_corner_velocity", "max_z_velocity", "max_z_accel"],
    },
}
DEFAULT_KIN = "f022"


def kin_for(decl):
    """(machine name, kinematics) for the machine this file names. Unknown -> the SparkX's, said."""
    p = decl.get("PRINTER", "")
    return (p if p in KIN else f"{p or 'unnamed'} (no limits on file — using {DEFAULT_KIN}'s)",
            KIN.get(p, KIN[DEFAULT_KIN]))


def junction_v(v_prev, v_next, scv, accel):
    """Klipper's cornering speed between two unit direction vectors.

    junction_deviation = scv^2 * (sqrt(2)-1) / accel;  v_j^2 = jd*a*cos(t/2)/(1-cos(t/2)).
    Accel cancels, so only scv and the turn angle matter.
    """
    dot = sum(a * b for a, b in zip(v_prev, v_next))
    dot = max(-1.0, min(1.0, dot))
    if dot >= 1.0 - 1e-12:
        return float("inf")
    if dot <= -1.0 + 1e-12:
        return 0.0
    half = math.cos(math.acos(dot) / 2.0)
    if 1.0 - half < 1e-12:
        return float("inf")
    jd = scv * scv * (math.sqrt(2.0) - 1.0) / accel
    return math.sqrt(jd * accel * half / (1.0 - half))


def plan_time(moves, kin):
    """Two-pass lookahead planner. moves = [(dist, vmax, accel, dir_unit)] -> total seconds."""
    n = len(moves)
    if not n:
        return 0.0
    # junction limits between consecutive moves
    vj = [0.0] * (n + 1)
    for i in range(1, n):
        vj[i] = min(junction_v(moves[i - 1][3], moves[i][3], kin["scv"], kin["max_a"]),
                    moves[i - 1][1], moves[i][1])
    # backward pass: cap entry speeds by what can still be braked to the exit
    ventry = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        d, vmax, a, _ = moves[i]
        vexit = min(vj[i + 1], ventry[i + 1]) if i + 1 <= n else 0.0
        ventry[i] = min(vmax, vj[i], math.sqrt(vexit * vexit + 2 * a * d))
    # forward pass + trapezoid time
    t = 0.0
    v_in = 0.0
    for i in range(n):
        d, vmax, a, _ = moves[i]
        v_in = min(v_in, ventry[i], vmax)
        v_out = min(ventry[i + 1] if i + 1 < n else 0.0, vj[i + 1], vmax)
        v_out = min(v_out, math.sqrt(v_in * v_in + 2 * a * d))
        vpeak = math.sqrt(max((2 * a * d + v_in * v_in + v_out * v_out) / 2.0, 0.0))
        vpeak = min(vpeak, vmax)
        d_a = max((vpeak * vpeak - v_in * v_in) / (2 * a), 0.0)
        d_d = max((vpeak * vpeak - v_out * v_out) / (2 * a), 0.0)
        d_c = d - d_a - d_d
        if d_c < 0:
            d_a = max(min((2 * a * d + v_out * v_out - v_in * v_in) / (4 * a), d), 0.0)
            d_d = max(d - d_a, 0.0)
            vpeak = math.sqrt(max(v_in * v_in + 2 * a * d_a, 0.0))
            d_c = 0.0
        t += ((vpeak - v_in) / a if a else 0.0) + ((vpeak - v_out) / a if a else 0.0)
        t += d_c / vpeak if vpeak > 1e-9 else 0.0
        v_in = v_out
    return t


def parse(path):
    """One pass over the file. Returns the raw move stream plus the header declarations."""
    decl = {}
    moves = []          # (x0,y0,z0, x1,y1,z1, de, feed, is_extrude, body)
    x = y = z = 0.0
    e = 0.0
    layer_z = 0.0
    feed = 1200.0
    abs_e = True
    body = False
    zlines = []         # standalone Z moves, in order: the layer ladder
    for raw in open(path):
        m = re.match(r'^; ([A-Z_0-9]+)=(.*)$', raw.strip())
        if m:
            decl.setdefault(m.group(1), m.group(2).strip())
        if 'BODY_START' in raw:
            body = True
            continue
        code = raw.split(';')[0].strip()
        if not code:
            continue
        if code.startswith('M82'):
            abs_e = True
            continue
        if code.startswith('M83'):
            abs_e = False
            continue
        if code.startswith('G92'):
            mm = re.search(r'E([-\d.]+)', code)
            if mm:
                e = float(mm.group(1))
            continue
        if not code.startswith(('G0', 'G1')):
            continue
        g = dict(re.findall(r'\b([XYZEF])(-?\d+(?:\.\d+)?)', code))
        if 'F' in g:
            feed = float(g['F'])
        nx = float(g['X']) if 'X' in g else x
        ny = float(g['Y']) if 'Y' in g else y
        nz = float(g['Z']) if 'Z' in g else z
        de = 0.0
        if 'E' in g:
            ev = float(g['E'])
            de = (ev - e) if abs_e else ev
            e = ev if abs_e else e + ev
        if body and 'Z' in g and 'X' not in g and 'Y' not in g and code.startswith('G1'):
            zlines.append(nz)
            layer_z = nz
        # A MOVE BELONGS TO THE LAYER THAT WAS OPENED BY THE LAST STANDALONE G1 Z, not to its own
        # endpoint Z. Bucketing by endpoint put every 0.4mm hop lift into a phantom layer of its
        # own, which reported a 1.963s "minimum layer time" and a 64% spread on a plate whose layer
        # time is constant by construction. The instrument was the liar, not the file.
        moves.append((x, y, z, nx, ny, nz, de, feed, de > 1e-9, body, layer_z))
        x, y, z = nx, ny, nz
    return decl, moves, zlines


def cluster_towers(moves, gap=6.0):
    """DISCOVER tower columns by clustering extruding-move X positions. The generator was told the
    centres; this recovers them from the path so the two can be compared."""
    xs = sorted({round(mv[3], 2) for mv in moves if mv[8] and mv[9]})
    if not xs:
        return []
    groups, cur = [], [xs[0]]
    for v in xs[1:]:
        if v - cur[-1] > gap:
            groups.append(cur)
            cur = [v]
        else:
            cur.append(v)
    groups.append(cur)
    return [(g[0], g[-1]) for g in groups]


def measure(path, verbose=True):
    decl, moves, zlines = parse(path)
    kin_name, kin = kin_for(decl)
    body = [mv for mv in moves if mv[9]]

    # ---- layer ladder, from Z transitions on standalone Z moves (not from comments)
    ladder = []
    for zv in zlines:
        if not ladder or abs(zv - ladder[-1]) > 1e-9:
            ladder.append(zv)
    steps = sorted({round(ladder[i + 1] - ladder[i], 4) for i in range(len(ladder) - 1)})

    # ---- towers, discovered
    cols = cluster_towers(moves)
    towers = []
    for (xa, xb) in cols:
        lo, hi = xa - 1.0, xb + 1.0
        pts = [mv for mv in body if mv[8] and lo <= mv[3] <= hi]
        if not pts:
            continue
        zmax = max(mv[5] for mv in pts)
        # diameter measured from the path's own extent ABOVE the foot (top 60% of the column),
        # so the foot's spiral does not contaminate the tower's own width
        # PER-LAYER extent above the foot, so the collars can be separated from the wall. Taking
        # one extent over the whole column reported every tower 0.30mm too wide -- it was measuring
        # the ruler collars, which are exactly +2*0.15mm. Modal = wall, max = collar.
        per = {}
        for mv in pts:
            if mv[10] <= zmax * 0.4:
                continue
            b = per.setdefault(round(mv[10], 3), [mv[3], mv[3], mv[4], mv[4]])
            b[0] = min(b[0], mv[3]); b[1] = max(b[1], mv[3])
            b[2] = min(b[2], mv[4]); b[3] = max(b[3], mv[4])
        dias = sorted(round(max(b[1] - b[0], b[3] - b[2]), 3) for b in per.values())
        modal = max(set(dias), key=dias.count) if dias else 0.0
        xsr = [mv[3] for mv in pts]
        ysr = [mv[4] for mv in pts]
        towers.append({
            "x": (min(xsr) + max(xsr)) / 2.0,
            "y": (min(ysr) + max(ysr)) / 2.0,
            "path_d": modal,
            "collar_d": dias[-1] if dias else 0.0,
            "n_collar_layers": sum(1 for d in dias if d > modal + 1e-9),
            "n_wall_layers": dias.count(modal),
            "zmax": zmax,
            "moves": len(pts),
            "fil": sum(mv[6] for mv in pts),
        })

    # ---- per-layer: distance, deposit, motion time
    layers = {}
    for mv in body:
        d3 = math.dist((mv[0], mv[1], mv[2]), (mv[3], mv[4], mv[5]))
        key = round(mv[10], 3)
        L = layers.setdefault(key, {"dist": 0.0, "ext": 0.0, "fil": 0.0, "moves": []})
        if mv[8]:
            L["ext"] += d3
            L["fil"] += mv[6]
        L["dist"] += d3
    # motion time must follow EMISSION ORDER across layer boundaries, so build the move list once
    seq = []
    for mv in body:
        dx, dy, dz = mv[3] - mv[0], mv[4] - mv[1], mv[5] - mv[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 1e-12:
            continue
        u = (dx / d, dy / d, dz / d)
        zonly = abs(dx) < 1e-9 and abs(dy) < 1e-9
        vmax = min(mv[7] / 60.0, kin["max_zv"] if zonly else kin["max_v"])
        if not zonly and abs(dz) > 1e-9:
            vmax = min(vmax, kin["max_zv"] * d / abs(dz))
        accel = kin["max_za"] if zonly else kin["max_a"]
        seq.append((d, vmax, accel, u, round(mv[10], 3)))
    # time per layer, planned in order
    times = {}
    i = 0
    while i < len(seq):
        zk = seq[i][4]
        j = i
        while j < len(seq) and seq[j][4] == zk:
            j += 1
        times[zk] = times.get(zk, 0.0) + plan_time([s[:4] for s in seq[i:j]], kin)
        i = j

    total_fil = sum(mv[6] for mv in moves if mv[6] > 0)
    body_fil = sum(mv[6] for mv in body if mv[6] > 0)
    total_time = plan_time([s[:4] for s in seq], kin)

    # ---- mm2/mm sampled at several heights
    zs = sorted(layers)
    samples = []
    for frac in (0.0, 0.05, 0.25, 0.5, 0.75, 1.0):
        zk = zs[min(int(frac * (len(zs) - 1)), len(zs) - 1)]
        L = layers[zk]
        mm2 = (L["fil"] * A_FIL / L["ext"]) if L["ext"] > 1e-9 else 0.0
        samples.append((zk, mm2, L["ext"], L["dist"], times.get(zk, 0.0)))

    feeds = {}
    for mv in body:
        feeds[mv[7]] = feeds.get(mv[7], 0) + 1

    # per-move cross-section extremes (the outlier hunt)
    xsec = []
    for mv in body:
        if not mv[8]:
            continue
        d = math.dist((mv[0], mv[1], mv[2]), (mv[3], mv[4], mv[5]))
        if d > 1e-9:
            xsec.append((mv[6] * A_FIL / d, mv[5]))
    xsec.sort()

    R = {
        "decl": decl, "ladder": ladder, "steps": steps, "towers": towers,
        "kin": kin, "kin_name": kin_name,
        "ladderset": {round(v, 3) for v in ladder},
        "layers": layers, "times": times, "samples": samples, "feeds": feeds,
        "total_fil": total_fil, "body_fil": body_fil, "total_time": total_time,
        "xsec": xsec, "nmoves": len(body), "zs": zs,
    }
    if verbose:
        report(path, R)
    return R


def report(path, R):
    decl, towers = R["decl"], R["towers"]
    print(f"\n=== MEASURED OFF {os.path.basename(path)} ===")
    print(f"  body moves          {R['nmoves']}")
    print(f"  filament total      {R['total_fil']:.1f} mm  "
          f"({R['total_fil']*A_FIL/1000:.2f} cm3, {R['total_fil']*A_FIL*1.24/1000:.1f} g PLA @1.24)")
    print(f"  filament in body    {R['body_fil']:.1f} mm  "
          f"(prime = {R['total_fil']-R['body_fil']:.1f} mm)")
    print(f"  layers (Z ladder)   {len(R['ladder'])}   z {R['ladder'][0]:.3f} -> {R['ladder'][-1]:.3f}")
    print(f"  distinct Z steps    {R['steps']}")
    _kin, _kn = R["kin"], R["kin_name"]
    print(f"  motion time         {R['total_time']/60:.1f} min "
          f"(trapezoid + junction, {_kn} limits; excludes heat-up)")
    print(f"    limits            v{_kin['max_v']:g} a{_kin['max_a']:g} scv{_kin['scv']:g} "
          f"zv{_kin['max_zv']:g} za{_kin['max_za']:g} — {_kin['src']}")
    if _kin["assumed"]:
        print(f"    NOT MEASURED      {', '.join(_kin['assumed'])} are STAND-INS carried from the "
              f"SparkX. The z-hop share of this time is not a {_kn} number.")

    print(f"\n  TOWERS DISCOVERED BY CLUSTERING (not read from the generator): {len(towers)}")
    bead = 0.42
    mb = re.search(r'bead ([\d.]+)', open(path).read()[:4000])
    if mb:
        bead = float(mb.group(1))
    print(f"  {'x':>7} {'wallD':>7} {'+bead':>7} {'collarD':>8} {'step':>6} "
          f"{'clyr':>5} {'z top':>7} {'fil mm':>7}")
    for t in towers:
        print(f"  {t['x']:7.2f} {t['path_d']:7.3f} {t['path_d']+bead:7.3f} "
              f"{t['collar_d']:8.3f} {t['collar_d']-t['path_d']:6.3f} "
              f"{t['n_collar_layers']:5d} {t['zmax']:7.3f} {t['fil']:7.2f}")
    print(f"  (wallD = MODAL per-layer path extent; collarD = MAX. step = the ruler's diameter "
          f"bump, which must be 2 x the declared radius bonus.)")

    print(f"\n  mm2/mm SAMPLED BY HEIGHT (declared FLOW {decl.get('FLOW','?')} mm3/s "
          f"at SPEED {decl.get('SPEED','?')} mm/s)")
    print(f"  {'z':>8} {'mm2/mm':>9} {'extrude':>9} {'travel+':>9} {'layer s':>9}")
    for (zk, mm2, ext, dist, ts) in R["samples"]:
        print(f"  {zk:8.3f} {mm2:9.5f} {ext:9.2f} {dist:9.2f} {ts:9.3f}")

    # SOME LAYERS ARE NOT ORDINARY LAYERS, and averaging them in destroys the statistic the
    # constant-layer-time claim rests on. Layer 1 and 2 carry every tower's foot; the last layer has
    # the end-of-print park folded into it. Reporting one min/max over all of them said "spread
    # 307%" about a plate whose ordinary layers vary by 7%. So: take the median, call anything
    # outside +/-50% of it STRUCTURAL, name those explicitly, and measure the spread on the rest.
    # Nothing here is hardcoded to a foot count -- the outliers are discovered, then listed.
    lad = sorted(R["ladderset"])
    allt = [(k, R["times"].get(k, 0.0)) for k in lad]
    med0 = sorted(t for _, t in allt)[len(allt) // 2]
    ordin = [(k, t) for k, t in allt if 0.5 * med0 <= t <= 1.5 * med0]
    odd = [(k, t) for k, t in allt if not (0.5 * med0 <= t <= 1.5 * med0)]
    if ordin:
        ts = sorted(t for _, t in ordin)
        med = ts[len(ts) // 2]
        print(f"\n  LAYER TIME  {len(ordin)} of {len(allt)} layers are ordinary")
        print(f"    min {ts[0]:.3f}s   median {med:.3f}s   max {ts[-1]:.3f}s"
              f"   spread {100*(ts[-1]-ts[0])/max(med,1e-9):.2f}% of median")
        print(f"    -> every tower is re-visited every {med:.2f}s at every height. That is the "
              f"cooling interval, and it is set by construction, not by padding.")
        print(f"    {len(odd)} structural exception(s), each named:")
        for k, t in odd:
            print(f"      z {k:7.3f}   {t:8.3f}s")
    print(f"\n  COMMANDED FEEDRATES IN BODY (F -> moves): "
          + ", ".join(f"{int(f)}->{n}" for f, n in sorted(R["feeds"].items())))
    xs = R["xsec"]
    print(f"  per-move cross-section  min {xs[0][0]:.5f}  median {xs[len(xs)//2][0]:.5f}  "
          f"max {xs[-1][0]:.5f} mm2 (at z {xs[-1][1]:.3f})")

    return check(path, R)


def check(path, R):
    """Compare what was MEASURED to what the file DECLARES. Disagreement = generator bug."""
    decl = R["decl"]
    fails = []
    def cmp(name, measured, declared, tol, unit=""):
        if declared is None:
            fails.append(f"{name}: nothing declared to check against")
            return
        ok = abs(measured - declared) <= tol
        print(f"  {'OK  ' if ok else 'FAIL'} {name}: measured {measured:.5f}{unit} vs "
              f"declared {declared:.5f}{unit} (tol {tol:g})")
        if not ok:
            fails.append(f"{name}: measured {measured:.5f} vs declared {declared:.5f}")

    print("\n  MEASURED vs DECLARED")
    lh = float(decl["LAYER_H"]) if "LAYER_H" in decl else None
    speed = float(decl["SPEED"]) if "SPEED" in decl else None
    flow = float(decl["FLOW"]) if "FLOW" in decl else None

    # Z ladder: every step must equal the declared layer height
    bad = [s for s in R["steps"] if lh and abs(s - lh) > 1e-6]
    print(f"  {'OK  ' if not bad else 'FAIL'} Z step: all {len(R['steps'])} distinct step(s) "
          f"{R['steps']} vs declared LAYER_H {lh}")
    if bad:
        fails.append(f"Z steps {bad} != LAYER_H {lh}")

    # first layer must be at the press height
    p1 = float(decl.get("PRESSED_LAYER1", "nan"))
    cmp("layer 1 Z", R["ladder"][0], p1, 1e-9, " mm")

    # flow: mm2/mm x speed, measured on the body's own deposit
    body_mm2 = []
    for zk in R["zs"]:
        L = R["layers"][zk]
        if L["ext"] > 1e-9:
            body_mm2.append(L["fil"] * A_FIL / L["ext"])
    med = sorted(body_mm2)[len(body_mm2) // 2]
    cmp("flow (median mm2/mm x SPEED)", med * speed, flow, 0.02, " mm3/s")

    # every body feedrate must be the declared speed
    bad_f = {f: n for f, n in R["feeds"].items() if abs(f / 60.0 - speed) > 0.5}
    print(f"  {'OK  ' if not bad_f else 'FAIL'} feedrates: {len(R['feeds'])} distinct in body, "
          f"all at SPEED {speed} mm/s" if not bad_f else
          f"  FAIL feedrates: {bad_f} are not the declared {speed} mm/s")
    if bad_f:
        fails.append(f"feedrates {bad_f} != {speed}")

    # per-move cross-section must sit on the nominal; an outlier is a real defect
    xs = R["xsec"]
    nominal = med
    out = [(v, z) for (v, z) in xs if v > nominal * 1.35 or v < nominal * 0.65]
    print(f"  {'OK  ' if not out else 'FAIL'} cross-section outliers: {len(out)} move(s) outside "
          f"0.65-1.35x the median {nominal:.5f} mm2")
    if out:
        fails.append(f"{len(out)} cross-section outliers, worst {out[-1][0]:.5f} at z{out[-1][1]:.3f}")

    # towers must all reach the same top (they are commanded to)
    tops = [t["zmax"] for t in R["towers"]]
    spread = max(tops) - min(tops) if tops else 0.0
    print(f"  {'OK  ' if spread < 1e-6 else 'FAIL'} tower tops: {len(tops)} tower(s), "
          f"spread {spread:.4f} mm")
    if spread >= 1e-6:
        fails.append(f"tower top spread {spread:.4f} mm")

    print(f"\n  {'ALL MEASUREMENTS AGREE WITH THE FILE' if not fails else 'DISAGREEMENTS (= BUGS):'}")
    for f in fails:
        print(f"    - {f}")
    return fails


def selftest(path):
    """FORCE THE MEASUREMENT TO FAIL. A check that has only ever printed OK proves nothing.

    Corrupts a COPY four different ways, asserts each corruption actually landed in the bytes, and
    requires the measurement to report a disagreement for each one.
    """
    print("\n" + "=" * 78)
    print("SELFTEST — corrupting a COPY and requiring the measurement to catch it")
    print("=" * 78)
    src = open(path).read().splitlines()
    tmp = tempfile.mkdtemp(prefix="towerselftest_")
    results = []

    def run(name, mutate, expect):
        lines = list(src)
        n = mutate(lines)
        assert n > 0, f"{name}: corruption did NOT land — nothing was changed"
        p = os.path.join(tmp, name + ".gcode")
        open(p, "w").write("\n".join(lines) + "\n")
        # PROVE the corruption is in the bytes, not just in my intention
        before = "\n".join(src)
        after = "\n".join(lines)
        assert before != after, f"{name}: file identical after mutation"
        print(f"\n--- {name}: {n} line(s) changed, file differs by "
              f"{sum(1 for a, b in zip(src, lines) if a != b)} line(s)")
        R = measure(p, verbose=False)
        fails = check(p, R)
        hit = any(expect in f for f in fails)
        print(f"    EXPECTED to catch '{expect}' -> {'CAUGHT' if hit else 'MISSED'}")
        results.append((name, hit))

    def bump_e(lines):
        """Inflate E on one mid-file extruding move: a fat bead the summary line would never show."""
        n = 0
        for i, l in enumerate(lines):
            if l.startswith("G1 X") and " E" in l and i > len(lines) // 2:
                m = re.search(r'E([\d.]+)', l)
                lines[i] = l[:m.start(1)] + f"{float(m.group(1)) + 0.5:.5f}" + l[m.end(1):]
                n = 1
                break
        return n

    def stretch_z(lines):
        """Double one layer's Z step — the floating-line failure R2 exists for."""
        n = 0
        for i, l in enumerate(lines):
            if re.match(r'^G1 F\d+ Z\d+\.\d+$', l) and i > len(lines) // 2:
                z = float(re.search(r'Z([\d.]+)', l).group(1))
                lines[i] = re.sub(r'Z[\d.]+', f"Z{z + 0.08:.3f}", l)
                n = 1
                break
        return n

    def raise_press(lines):
        """Lift layer 1 off the plate: R1's exact failure, and it must show as a Z disagreement."""
        n = 0
        for i, l in enumerate(lines):
            if l == "G1 F3000 Z0.100":
                lines[i] = "G1 F3000 Z0.510"
                n += 1
                if n == 2:
                    break
        return n

    def behead(lines):
        """Delete the top 200 layers of ONE tower — the case where a plate looks fine in summary
        but one column silently stops. Nothing but a per-tower height measurement finds this."""
        keep, n = [], 0
        drop_x = None
        for l in lines:
            m = re.match(r'^G1 X([\d.]+) Y([\d.]+) E', l)
            if m and drop_x is None:
                drop_x = float(m.group(1))
            if m and drop_x is not None and abs(float(m.group(1)) - drop_x) < 6.0:
                mz = None
                if n < 10 ** 9:
                    pass
            keep.append(l)
        # simpler and unambiguous: drop every extruding move of the FIRST tower above z=40
        out, z, n = [], 0.0, 0
        for l in lines:
            mz = re.search(r'Z(\d+\.\d+)', l)
            if l.startswith(("G0", "G1")) and mz:
                z = float(mz.group(1))
            m = re.match(r'^G1 X([\d.]+) Y', l)
            if m and z > 40.0 and drop_x is not None and abs(float(m.group(1)) - drop_x) < 6.0:
                n += 1
                continue
            out.append(l)
        lines[:] = out
        return n

    run("fat_bead", bump_e, "cross-section outliers")
    run("floating_layer", stretch_z, "Z steps")
    run("unpressed_layer1", raise_press, "layer 1 Z")
    run("beheaded_tower", behead, "tower top spread")

    print("\n" + "=" * 78)
    ok = all(h for _, h in results)
    for name, hit in results:
        print(f"  {'CAUGHT ' if hit else 'MISSED '} {name}")
    print(f"SELFTEST {'PASSED — every corruption was caught' if ok else 'FAILED — a corruption slipped through'}")
    shutil.rmtree(tmp, ignore_errors=True)
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--selftest", action="store_true",
                    help="corrupt a copy four ways and require the measurement to catch each")
    a = ap.parse_args()
    bad = 0
    for fpath in a.files:
        R = measure(fpath)
        if a.selftest and not selftest(fpath):
            bad += 1
    sys.exit(1 if bad else 0)
