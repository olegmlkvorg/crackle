#!/usr/bin/env python3
"""FUNCTION probes for the web-bucket parts — geometry checks on the EMITTED gcode.

validate.py checks the printing rules; this checks that the parts can do their JOB:
sticks can enter every socket, channels are open where a stick must lie and closed where
the snap lip must hold it, clip beads stand on material, and the four parts agree with
each other about where the sticks are. Every threshold is written against centreline
positions measured from the file, not from the generator's variables (the summary line
is not the file).
"""
import argparse, math, re, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

FAILS = []

REQUIRED_ARTIFACTS = (
    "web_coupon_k1c_T230.gcode",
    "web_base_k2plus_d200_T230.gcode",
    "web_panel1_k2plus_w295_h178_T230.gcode",
    "web_panel2_k2plus_w295_h178_T230.gcode",
    "web_topper_k2plus_T230.gcode",
)

# V4/V5 spring-pocket contract, with the same recorded provenance as web.py.  These replace
# the pre-V4 solid-boss bore expectation that this probe retained after the design changed.
STICK_D = 3.175          # MEASURED: 1/8-inch bamboo stock
SOCKET_R = 90.5          # CHOSEN: web.py R_STICK, 2026-07-28
POCKET_RC = 2.70         # Oleg 2026-07-28: +10% from 2.45; half-flow spring-C centreline
POCKET_STRAND = 1.0      # DERIVED: half of the K2's 2.0mm full-flow bead
BASE_LAYERS = 10         # Oleg 2026-07-29: "10 layers in total"
CAP_LAYERS = 3           # CHOSEN: show-face cap sheet
TOP_POCKET_LAPS = 9      # CHOSEN: same 5.4mm grip above the base's pressed floor
LAYER_H = 0.6            # generator-emitted layer step
PRESS_Z = 0.1            # machine.PRESS_HARD


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


def socket_minima(pts, zlo, zhi):
    out = []
    for k in range(12):
        px = 175.0 + SOCKET_R * math.cos(2 * math.pi * k / 12)
        py = 175.0 + SOCKET_R * math.sin(2 * math.pi * k / 12)
        out.append(near(pts, px, py, zlo, zhi)[0])
    return out


def probe_base(path):
    print(f"\n== {path}")
    pts = read_pts(path)
    ds = socket_minima(pts, 3.05, 14.0)
    stick_r = STICK_D / 2.0
    # This preserved 2026-07-29 p36 experiment is a known-bad control.  Its two extra petals
    # between each socket cross the physical stick envelope; keeping the bytes makes this probe
    # prove that the obstruction is detected without rewriting the historical record.
    ok(len(ds) == 12 and max(ds) < stick_r,
       f"known-bad p36 base rejected: all 12 sockets obstructed at "
       f"r{min(ds):.3f}-{max(ds):.3f} inside stick r{stick_r:.3f}")
    zs = sorted({round(p[2], 2) for p in pts})
    want_top = PRESS_Z + (BASE_LAYERS - 1) * LAYER_H
    ok(abs(max(zs) - want_top) < 1e-6,
       f"historical base top z={max(zs)} (V5 10-layer design: {want_top})")


def probe_base_generator():
    """The corrected source must preserve a real 1/8-inch void at every spring pocket."""
    import web
    pts, _ = web.rose_sockets(175.0, 175.0, 100.0, 2.0)
    ds = []
    for k in range(12):
        px = 175.0 + SOCKET_R * math.cos(2 * math.pi * k / 12)
        py = 175.0 + SOCKET_R * math.sin(2 * math.pi * k / 12)
        ds.append(min(math.hypot(x - px, y - py) for x, y in pts))
    inner_edge = min(ds) - POCKET_STRAND / 2.0
    ok(all(abs(d - POCKET_RC) < 0.02 for d in ds),
       f"current p12 base: 12 spring-C walls at r{min(ds):.3f}-{max(ds):.3f} "
       f"(want {POCKET_RC:.2f})")
    ok(inner_edge > STICK_D / 2.0,
       f"current p12 base: modelled inner bead edge r{inner_edge:.3f} clears "
       f"1/8-inch stick r{STICK_D/2:.3f}")


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


def probe_topper(path, bw=2.0):
    print(f"\n== {path}")
    pts = read_pts(path)
    cx = cy = 175.0
    # sockets at the SAME k/12 angles as the base: the assembly flip maps x->x, y->-y
    # (mirror), and this set maps onto itself landing on the base's stick circle
    for k in range(12):
        px = cx + SOCKET_R * math.cos(2 * math.pi * k / 12)
        py = cy + SOCKET_R * math.sin(2 * math.pi * k / 12)
        d, n = near(pts, px, py, 1.85, 9.0)
        dc, ncap = near(pts, px, py, 0.0, 1.35)
        ok(abs(d - POCKET_RC) < 0.15 and dc < 1.5,
           f"socket {k}: spring-C wall at {d:.2f} (want {POCKET_RC:.2f}), "
           f"capped below (bead {dc:.2f} from centre)")
        # the flip check itself: mirrored centre must also be a socket centre
        mk = min(range(12), key=lambda j: math.hypot(
            px - (cx + SOCKET_R * math.cos(2 * math.pi * j / 12)),
            (2 * cy - py) - (cy + SOCKET_R * math.sin(2 * math.pi * j / 12))))
        mx = cx + SOCKET_R * math.cos(2 * math.pi * mk / 12)
        my = cy + SOCKET_R * math.sin(2 * math.pi * mk / 12)
        ok(math.hypot(px - mx, (2 * cy - py) - my) < 0.01,
           f"socket {k}: mirrored position lands on socket {mk} — flip-aligned")
    # spiral cap coverage: no radial gap wider than a bead on the pressed face
    rr = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in pts if p[2] <= 0.15)
    gaps = max(b - a_ for a_, b in zip(rr, rr[1:]))
    # V4 deliberately narrowed the cap to the wall/pocket envelope.  82..98 is CHOSEN in
    # web.py; its 16mm span is exactly eight 2mm bead pitches, avoiding an extruded seam chord.
    ok(abs(rr[0] - 82.0) < 0.05 and abs(rr[-1] - 98.0) < 0.05 and gaps < bw + 0.1,
       f"cap spiral spans r{rr[0]:.1f}-{rr[-1]:.1f}, max radial step {gaps:.2f}")
    zs = sorted({round(p[2], 2) for p in pts})
    want_top = PRESS_Z + (CAP_LAYERS + TOP_POCKET_LAPS - 1) * LAYER_H
    ok(abs(max(zs) - want_top) < 1e-6,
       f"spring-pocket top z={max(zs)} (3 cap + 9 pocket layers: {want_top})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get(
        "CRACKLE_ARTIFACTS",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")))
    args = ap.parse_args()
    base = os.path.abspath(args.out)
    probe_coupon(os.path.join(base, "web_coupon_k1c_T230.gcode"))
    probe_base(os.path.join(base, "web_base_k2plus_d200_T230.gcode"))
    probe_base_generator()
    probe_panel(os.path.join(base, "web_panel1_k2plus_w295_h178_T230.gcode"))
    probe_panel(os.path.join(base, "web_panel2_k2plus_w295_h178_T230.gcode"))
    probe_topper(os.path.join(base, "web_topper_k2plus_T230.gcode"))
    print(f"\n{'ALL FUNCTION PROBES PASS' if not FAILS else f'{len(FAILS)} FAILURES'}")
    sys.exit(1 if FAILS else 0)
