#!/usr/bin/env python3
"""TRANSFER TROUGH -- the piece that makes a marble run a STRUCTURE rather than a stack.

Takes the marble leaving the bottom of one tower and runs it sideways and downhill into the top of
a shorter neighbouring tower, so a run cascades across towers standing on one base plate.

WHAT DECIDES THE DESIGN, in order:

 1. TRANSIT, because that is the failure that reached Oleg's hands this week. A bend guide passed
    six checks including one named "threadable" and could not admit a stick. So the first gate here
    measures the FREE CHANNEL along the whole path off the emitted mesh, at the worst point,
    against a real marble, and it is checked by a route that does not reuse the numbers that built
    the part. See Assist/guides/retro-bore-transit.md.

 2. GRADE. Too shallow and the marble stops, too steep and it launches off the end. The chute's
    gutter measures ~21 deg and moves reliably, but a gutter is a helix where the marble is also
    held by centripetal force, so that figure is a data point and not an answer. A free trough only
    needs to beat rolling resistance, which for a hard sphere on hard plastic is small, so the
    grade here is DERIVED from the drop the geometry already forces: the run must fall by one
    coupling engagement plus clearance over one grid span, and that comes out near 12 deg. Steep
    enough to move, shallow enough that exit speed stays low. ASSUMED: that a marble which moves at
    21 deg on a curved gutter also moves at 12 deg on a straight one. A coupon settles it.

 3. THE MARBLE MUST NOT CLIMB OUT ON THE CORNER. A ball entering a curve is thrown outward, so the
    outer wall has to be taller than the inner. Height is DERIVED from the sideways force at the
    measured exit speed, not picked.

Prints LYING DOWN, channel facing up: the underside is flat on the bed, the channel is an open
groove, and nothing overhangs. Class `closed` for qa_stl.

Usage: python3 transfer_stl.py [--spans 1] [--slim] [--marble 16]
"""
import argparse, math, os, struct

import marble_common as mc

WALL      = 2.0      # trough wall; thicker than a vase bead because this one gets knocked
FLOOR     = 2.4      # under the channel
CLEAR     = 3.0      # radial air around the marble in the channel
G         = 9.81
ROLL_MU   = 0.02     # rolling resistance, hard sphere on hard plastic. ASSUMED, handbook range
                     # 0.01-0.03. It only has to be beaten, and 12 deg beats it by ~30x.


def normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"crackle transfer - marble trough, tower to tower".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", *normal(*t)))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


def section(x, ch_r, h_in, h_out, drop_at):
    """Cross-section at distance x along the run, as an ordered (y, z) polygon, channel opening
    upward. z=0 is the underside. The channel floor follows the grade."""
    z0 = drop_at(x)
    pts = []
    n = 16
    for i in range(n + 1):                       # channel bowl, a half-round groove
        a = math.pi * (1.0 - i / n)              # pi -> 0, so y runs -ch_r to +ch_r
        pts.append((ch_r * math.cos(a), z0 + FLOOR + ch_r - ch_r * math.sin(a)))
    inner = (ch_r + WALL, z0 + FLOOR + ch_r + h_in)
    outer = (-ch_r - WALL, z0 + FLOOR + ch_r + h_out)
    return ([( -ch_r - WALL, 0.0 ), ( ch_r + WALL, 0.0 ), (ch_r + WALL, inner[1]),
             (ch_r, inner[1])] + pts[::-1] + [(-ch_r, outer[1]), (-ch_r - WALL, outer[1])])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spans", type=int, default=1, help="grid spans to cross")
    ap.add_argument("--slim", action="store_true", help="slim coupling standard")
    ap.add_argument("--marble", type=float, default=mc.MARBLE_D)
    ap.add_argument("--grade", type=float, default=None, help="deg; default DERIVED")
    ap.add_argument("--force-channel", type=float, default=None, metavar="R",
                    help="pin the channel radius instead of deriving it from the marble. The only "
                         "way to build a known-bad: the channel normally scales WITH the marble, "
                         "so asking for a bigger ball can never fail the transit check, which "
                         "would make that check decoration.")
    ap.add_argument("--steps", type=int, default=140)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.slim:
        mc.configure_bond(mc.min_bond_tip_d(40.8))
    span = mc.GRID_PITCH * a.spans
    ch_r = a.force_channel if a.force_channel is not None else a.marble / 2 + CLEAR

    # GRADE, derived: the run must fall by one engagement + clearance across the span, so the
    # receiving socket sits fully below the delivering exit.
    fall = mc.COUPLE_L + 4.0
    grade = a.grade if a.grade is not None else math.degrees(math.atan(fall / span))
    assert math.tan(math.radians(grade)) > ROLL_MU * 3, (
        f"grade {grade:.1f} deg does not beat rolling resistance with margin")

    drop = lambda x: (span - x) * math.tan(math.radians(grade))

    # exit speed from the drop, and the wall height that keeps the ball in on a curve
    v = math.sqrt(2 * G * (fall / 1000.0) * 5.0 / 7.0)       # rolling sphere, 5/7 of the energy
    h_out = max(a.marble * 0.55, (v * v) / (2 * G) * 1000.0 * 0.25)
    h_in = a.marble * 0.35
    out = a.out or f"transfer_{a.spans}span{'_slim' if a.slim else ''}.stl"

    tris = []
    prev = None
    for i in range(a.steps + 1):
        x = span * i / a.steps
        sec = section(x, ch_r, h_in, h_out, drop)[::-1]   # winding: normals must face OUT
        cur = [(x, y, z) for (y, z) in sec]
        if prev is not None:
            n = len(cur)
            for k in range(n):
                j = (k + 1) % n
                tris.append((prev[k], cur[k], cur[j]))
                tris.append((prev[k], cur[j], prev[j]))
        prev = cur
    for cap, flip in ((0, False), (a.steps, True)):           # end caps
        x = span * cap / a.steps
        sec = [(x, y, z) for (y, z) in section(x, ch_r, h_in, h_out, drop)[::-1]]
        c = (x, sum(p[1] for p in sec)/len(sec), sum(p[2] for p in sec)/len(sec))
        for k in range(len(sec)):
            j = (k + 1) % len(sec)
            tris.append((c, sec[j], sec[k]) if flip else (c, sec[k], sec[j]))

    write_stl(out, tris)

    # ---- self-verify: MEASURE off the emitted mesh, by a route the builder did not use ----
    with open(out, "rb") as f:
        f.read(80); (n,) = struct.unpack("<I", f.read(4))
        V = []
        for _ in range(n):
            f.read(12); V += [struct.unpack("<3f", f.read(12)) for _ in range(3)]; f.read(2)
    edges = {}
    for t in range(n):
        k3 = [tuple(round(c, 3) for c in V[3*t+i]) for i in range(3)]
        for i in range(3):
            e = tuple(sorted((k3[i], k3[(i+1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)

    # THE TRANSIT CHECK, third attempt, and the two wrong ones are kept in the comment because
    # each was a probe fault rather than a part fault.
    #   1st: took the band above min(z). The underside is flat at z=0 while the channel floor rises
    #        with the grade, so it measured the wedge's OUTSIDE and reported 4.29mm on a 22mm
    #        channel.
    #   2nd: took the widest air gap at ANY height. Above the wall tops there is nothing but air
    #        between two wall crowns, so it reported 26mm, the outer width.
    # The marble does not care about either. It sits with its CENTRE one radius above the channel
    # floor, and what must be >= its diameter is the free width AT THAT HEIGHT. So: find the
    # channel floor at each station as the lowest material that is not the flat underside, go up
    # one marble radius, and measure the air there.
    worst, worst_x = 1e9, None
    for i in range(1, 40):
        x = span * i / 40
        near = [q for q in V if abs(q[0] - x) < span / 80]
        if len(near) < 8:
            continue
        above = [q[2] for q in near if q[2] > 1.0]      # exclude the flat underside at z=0
        if not above:
            continue
        floor_z = min(above)
        zc = floor_z + a.marble / 2.0                   # where the marble's centre rides
        band = [q for q in near if abs(q[2] - zc) < 1.0]
        if len(band) < 4:
            continue
        ys = sorted(q[1] for q in band)
        gap = max((ys[k+1] - ys[k] for k in range(len(ys)-1)), default=0.0)
        if gap and gap < worst:
            worst, worst_x = gap, x

    L = max(p[0] for p in V); W = max(p[1] for p in V) - min(p[1] for p in V)
    H = max(p[2] for p in V)

    print(f"{out}: {n} tris | {L:.0f} x {W:.0f} x {H:.0f} mm, {a.spans} span(s) of "
          f"{mc.GRID_PITCH:.1f}mm, grade {grade:.1f} deg (DERIVED from a {fall:.0f}mm fall)")
    print(f"  exit speed {v*1000:.0f} mm/s; outer wall {h_out:.1f} vs inner {h_in:.1f} "
          f"(the ball is thrown outward)")
    checks = [
        ("watertight", open_edges == 0, f"{open_edges} open edges"),
        ("MARBLE PASSES", worst >= a.marble + 1.0,
         f"narrowest measured channel {worst:.2f}mm at x={worst_x:.0f} vs a O{a.marble:g} marble "
         f"(want >= {a.marble+1.0:.1f}). This is the check the bend guide did not have."),
        ("grade beats rolling", math.tan(math.radians(grade)) > ROLL_MU * 3,
         f"tan {math.tan(math.radians(grade)):.3f} vs {ROLL_MU*3:.3f} needed (ASSUMED mu {ROLL_MU})"),
        ("outer wall taller", h_out > h_in, f"{h_out:.1f} vs {h_in:.1f} mm"),
        ("prints flat", H <= a.marble * 2 + 12, f"{H:.0f}mm tall lying down"),
        ("bed fit", L <= 340 and W <= 340, f"{L:.0f} x {W:.0f} vs 340"),
    ]
    ok = True
    for nm, good, msg in checks:
        print("  %s %-20s %s" % ("PASS" if good else "FAIL", nm, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (print flat, channel up, no support)")


if __name__ == "__main__":
    main()
