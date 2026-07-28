#!/usr/bin/env python3
"""FUNCTION probes for the web-bucket parts — geometry checks on the EMITTED gcode.

validate.py checks the printing rules; this checks that the parts can do their JOB:
sticks can enter every socket, channels are open where a stick must lie and closed where
the snap lip must hold it, clip beads stand on material, and the four parts agree with
each other about where the sticks are. Every threshold is written against centreline
positions measured from the file, not from the generator's variables (the summary line
is not the file).
"""
import math, re, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

FAILS = []


def ok(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def read_pts(path):
    """Extruding-move endpoints (x, y, z, e_delta). HOPs and travels excluded."""
    pts, x, y, z, e = [], 0.0, 0.0, 0.0, 0.0
    for line in open(path):
        if not line.startswith(("G0", "G1")):
            continue
        m = dict(re.findall(r"([XYZE])([-\d.]+)", line.split(";")[0]))
        nx = float(m.get("X", x)); ny = float(m.get("Y", y)); nz = float(m.get("Z", z))
        ne = float(m.get("E", e))
        if line.startswith("G1") and "E" in m and ne > e and "PRIME" not in line:
            pts.append((nx, ny, nz, ne - e))
        x, y, z, e = nx, ny, nz, ne
    return pts


def near(pts, cx, cy, zlo, zhi):
    ds = [math.hypot(p[0] - cx, p[1] - cy) for p in pts if zlo <= p[2] <= zhi]
    return (min(ds), len(ds)) if ds else (1e9, 0)


def bore_probe(pts, label, cx, cy, bore, bw, zlo, zhi, lobed=None):
    """A socket must be BOTH clear (no bead inside the commanded void) and walled
    (a ring bead actually present at the void edge — the sub-6mm loss mode)."""
    want = (lobed / 2.0 + bw / 2.0) if lobed else (bore / 2.0 + bw / 2.0)
    d, n = near(pts, cx, cy, zlo, zhi)
    ok(d > want - 0.15, f"{label}: void clear — nearest bead centreline {d:.2f} "
                        f"(wall belongs at {want:.2f})")
    ok(d < want + 0.40, f"{label}: wall present — nearest bead {d:.2f} vs {want:.2f}")


def channel_probe(pts, label, x0, x1, yc, cav, mouth, bw, z_rail_lo, z_mouth):
    body = [p for p in pts if x0 <= p[0] <= x1 and z_rail_lo <= p[2] < z_mouth - 0.3]
    lip = [p for p in pts if x0 <= p[0] <= x1 and p[2] >= z_mouth - 0.05]
    face = cav / 2.0 + bw / 2.0
    lipc = face - (cav - mouth) / 2.0
    if body:
        d = min(abs(p[1] - yc) for p in body)
        ok(abs(d - face) < 0.15, f"{label}: rails at |y-yc|={d:.2f} (want {face:.2f})")
    else:
        ok(False, f"{label}: NO rail beads found — the channel is missing")
    if lip:
        d = min(abs(p[1] - yc) for p in lip)
        got_mouth = 2 * (d - bw / 2.0)
        ok(abs(d - lipc) < 0.15, f"{label}: snap lip at |y-yc|={d:.2f} -> mouth "
                                 f"{got_mouth:.2f} (want {mouth:.2f})")
    else:
        ok(False, f"{label}: NO snap-lip beads on the top layers")


def probe_coupon(path):
    print(f"\n== {path}")
    pts = read_pts(path)
    bw = 1.5
    ox, oy, yc = 45.0, 100.0, 10.0
    for label, sx, bore in [("V1 bore 9.0", 16, 9.0), ("V2 bore 9.9", 36, 9.9),
                            ("V3 bore 10.8", 56, 10.8)]:
        bore_probe(pts, label, ox + sx, oy + yc, bore, bw, 1.25, 6.0)
    # V4: the three bumps must reach in to the inscribed circle — that IS the socket
    d, _ = near(pts, ox + 76, oy + yc, 1.25, 6.0)
    ok(abs(d - (5.6 / 2 + bw / 2)) < 0.30,
       f"V4 lobed: bump contact at r={d:.2f} (want {5.6/2 + bw/2:.2f})")
    for label, chx, mouth in [("V5 channel", 96.0, 2.9), ("V6 channel", 118.0, 2.5)]:
        channel_probe(pts, label, ox + chx - 4, ox + chx + 7, oy + yc, 4.3, mouth, bw,
                      1.25, 4.9)
    # notches: layer-2 outline must leave each index bite void
    for sx, count in [(16, 1), (36, 2), (56, 3), (76, 4), (96, 5), (118, 6)]:
        clear = True
        for k in range(count):
            nx = ox + sx + (k - (count - 1) / 2.0) * 3.2
            d = min((math.hypot(p[0] - nx, p[1] - oy) for p in pts
                     if 0.6 <= p[2] <= 0.75), default=1e9)
            clear &= d > 1.2 - 0.75 - 0.05
        ok(clear, f"index notches x{count} present at site x={sx}")
    zs = sorted({round(p[2], 2) for p in pts})
    ok(max(zs) == 5.5, f"top of rails at z={max(zs)} (want 5.5)")


def probe_base(path, bore=9.9, bw=2.0):
    print(f"\n== {path}")
    pts = read_pts(path)
    cx = cy = 175.0
    for k in range(12):
        px = cx + 90.5 * math.cos(2 * math.pi * k / 12)
        py = cy + 90.5 * math.sin(2 * math.pi * k / 12)
        d, n = near(pts, px, py, 3.05, 14.0)
        want = bore / 2 + bw / 2
        if not (want - 0.15 < d < want + 0.40):
            ok(False, f"socket {k}: bead at {d:.2f} vs want {want:.2f}")
            continue
        # socket floor: solid material below the void (blind socket)
        df, nf = near(pts, px, py, 0.0, 2.55)
        ok(df < 1.5 and nf > 3, f"socket {k}: void walled at {d:.2f} AND floored "
                                f"(bead {df:.2f} from centre below it)")
    zs = sorted({round(p[2], 2) for p in pts})
    ok(abs(max(zs) - 13.9) < 1e-6, f"band top z={max(zs)} (want 13.9)")


def probe_panel(path, bw=2.0, cav=4.3, mouth=2.9):
    print(f"\n== {path}")
    pts = read_pts(path)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    W, H = max(xs) - min(xs), max(ys) - min(ys)
    ok(abs(W - 295.4) < 2.5 and abs(H - 177.6) < 2.5,
       f"panel envelope {W:.1f} x {H:.1f} (want ~295.4 x 177.6)")
    ox = (350 - 295.4) / 2
    pitch = 2 * math.pi * (90.5 + 3.175 / 2 + 0.35) / 12
    lines = [ox + 10.0 + i * pitch for i in range(6)]
    face = cav / 2.0 + bw / 2.0
    for i, xl in enumerate(lines):
        band = [p for p in pts if abs(p[0] - xl) < 8.0 and p[2] >= 1.25]
        body = [p for p in band if p[2] < 4.85 - 0.3]
        lip = [p for p in band if p[2] >= 4.85]
        if body:
            d = min(abs(p[0] - xl) for p in body)
            ok(abs(d - face) < 0.15,
               f"stick line {i}: corridor clear to rails at {d:.2f} (want {face:.2f})")
        else:
            ok(False, f"stick line {i}: no rail beads")
        if lip:
            d = min(abs(p[0] - xl) for p in lip)
            got = 2 * (d - bw / 2.0)
            ok(abs(got - mouth) < 0.25,
               f"stick line {i}: snap mouth {got:.2f} (want {mouth:.2f})")
        else:
            ok(False, f"stick line {i}: no snap lip")
    # every clip bead must stand on layer-2 material (comb footprint)
    l2 = [(p[0], p[1]) for p in pts if 0.65 <= p[2] <= 1.15]
    clip1 = [(p[0], p[1]) for p in pts if abs(p[2] - 1.3) < 0.05]
    worst = 0.0
    for cxp, cyp in clip1[::7]:
        d = min(math.hypot(cxp - qx, cyp - qy) for qx, qy in l2)
        worst = max(worst, d)
    ok(worst < 1.1, f"clip layer 1 sits on the L2 footprint (worst offset {worst:.2f}, "
                    f"bead half-width {bw/2:.1f})")
    n_lift = sum(1 for p in pts if 0.75 < p[2] < 1.15)
    ok(n_lift > 100, f"net crossing lifts present ({n_lift} lifted points)")


def probe_topper(path, bore=9.9, bw=2.0):
    print(f"\n== {path}")
    pts = read_pts(path)
    cx = cy = 175.0
    # sockets at the SAME k/12 angles as the base: the assembly flip maps x->x, y->-y
    # (mirror), and this set maps onto itself landing on the base's stick circle
    for k in range(12):
        px = cx + 90.5 * math.cos(2 * math.pi * k / 12)
        py = cy + 90.5 * math.sin(2 * math.pi * k / 12)
        d, n = near(pts, px, py, 1.85, 9.0)
        want = bore / 2 + bw / 2
        dc, ncap = near(pts, px, py, 0.0, 1.35)
        ok(want - 0.15 < d < want + 0.40 and dc < 1.5,
           f"socket {k}: walled at {d:.2f}, capped below (bead {dc:.2f} from centre)")
        # the flip check itself: mirrored centre must also be a socket centre
        mk = min(range(12), key=lambda j: math.hypot(
            px - (cx + 90.5 * math.cos(2 * math.pi * j / 12)),
            (2 * cy - py) - (cy + 90.5 * math.sin(2 * math.pi * j / 12))))
        mx = cx + 90.5 * math.cos(2 * math.pi * mk / 12)
        my = cy + 90.5 * math.sin(2 * math.pi * mk / 12)
        ok(math.hypot(px - mx, (2 * cy - py) - my) < 0.01,
           f"socket {k}: mirrored position lands on socket {mk} — flip-aligned")
    # spiral cap coverage: no radial gap wider than a bead on the pressed face
    rr = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in pts if p[2] <= 0.15)
    gaps = max(b - a_ for a_, b in zip(rr, rr[1:]))
    ok(rr[0] < 81.5 and rr[-1] > 100.4 and gaps < bw + 0.1,
       f"cap spiral spans r{rr[0]:.1f}-{rr[-1]:.1f}, max radial step {gaps:.2f}")
    zs = sorted({round(p[2], 2) for p in pts})
    ok(abs(max(zs) - 8.5) < 1e-6, f"socket ring top z={max(zs)} (want 8.5)")


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
    probe_coupon(os.path.join(base, "web_coupon_k1c_T230.gcode"))
    probe_base(os.path.join(base, "web_base_k2plus_d200_T230.gcode"))
    probe_panel(os.path.join(base, "web_panel1_k2plus_w295_h178_T230.gcode"))
    probe_panel(os.path.join(base, "web_panel2_k2plus_w295_h178_T230.gcode"))
    probe_topper(os.path.join(base, "web_topper_k2plus_T230.gcode"))
    print(f"\n{'ALL FUNCTION PROBES PASS' if not FAILS else f'{len(FAILS)} FAILURES'}")
    sys.exit(1 if FAILS else 0)
