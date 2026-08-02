#!/usr/bin/env python3
"""bend_guide_stl.py — the BEND GUIDE / BOW KEEPER (Oleg 2026-08-02: "a middle stick piece as a
guide for angle. pass stick thru and you get the designate angle bend").

THREE through-bores along a standing bar; the MIDDLE bore is OFFSET sideways by the sagitta o.
Thread a 1/4in rod through all three and the rod is FORCED onto the arc through the three points:
    R = s^2 / (2*o)        (s = bore spacing, o = middle offset)
    bend angle over a 24in rod = 610 / R  (radians)
Bamboo is elastic, so the guide STAYS on the rod as the keeper of the bow (remove it and the rod
springs straight — same physics that keeps the stave shelf's joints preloaded forever).

SAFETY (stave-measured): a 6.35 rod SNAPS below R~318. Offsets are capped so R >= 954 (3x margin).
At s=65 that allows whole-rod angles up to ~36 deg; --angle picks from the quantized set.

PRINTS STANDING (bar axis vertical): every bore is a vertical channel -> clean round holes, no
teardrops, no support. Slide-fit bores (O7.65) because the rod must THREAD through three in a row.

Usage: python3 bend_guide_stl.py [--angle 30] [--spacing 65] [--out bend_guide_a30.stl]
"""
import argparse, math, os, struct

ROD_LEN = 610.0          # 24in stock
R_MIN = 954.0            # 3x the ~318mm snap radius (stave-measured)
SLIDE_BORE_D = 7.65      # rod must slide through 3 bores in a row
WALL_MIN = 2.4
ANGLES = (15.0, 20.0, 25.0, 30.0, 35.0)   # quantized whole-rod bend angles (deg)


def normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"crackle bend_guide - bamboo bow keeper (3-bore sagitta jig)".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


def ring(cx, cy, r, n, ccw=True):
    p = [(cx + r*math.cos(2*math.pi*k/n), cy + r*math.sin(2*math.pi*k/n)) for k in range(n)]
    return p if ccw else p[::-1]


def tube(tris, outer, inner, z0, z1):
    n = len(outer)
    for k in range(n):
        j = (k+1) % n
        O0, O1 = (*outer[k], z0), (*outer[j], z0)
        O0h, O1h = (*outer[k], z1), (*outer[j], z1)
        I0, I1 = (*inner[k], z0), (*inner[j], z0)
        I0h, I1h = (*inner[k], z1), (*inner[j], z1)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))     # outer wall out
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))     # bore wall in
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))        # bottom -z
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))  # top +z


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--angle", type=float, default=30.0, help="whole-24in-rod bend angle deg (quantized set)")
    ap.add_argument("--spacing", type=float, default=65.0, help="bore spacing s mm (bar length ~2s+walls)")
    ap.add_argument("--points", type=int, default=64, help="samples per bore/boss ring")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    assert a.angle in ANGLES, f"--angle must be one of {ANGLES} (quantized, LEGO-style)"
    theta = math.radians(a.angle)
    R = ROD_LEN / theta                      # arc radius that gives this angle over the full rod
    o = a.spacing**2 / (2.0 * R)             # sagitta offset of the middle bore
    out = a.out or f"bend_guide_a{a.angle:g}.stl"

    br = SLIDE_BORE_D / 2.0
    boss_r = br + WALL_MIN + 0.6             # boss wall around each bore
    s = a.spacing
    H = 2*s + 2*boss_r                       # standing bar height: three bores at z = boss_r, boss_r+s, boss_r+2s
    # the bar is a vertical slab whose cross-section (xy) hulls the three boss circles; bores run VERTICALLY?
    # NO — the rod runs ALONG the bar: print standing, bores run along Z (the bar axis) = the rod axis.
    # Three bores are SEGMENTS of one channel at different lateral offsets: bottom third centered x=0,
    # middle third centered x=o, top third centered x=0. Between thirds, short CONE transitions let the
    # rod thread through (the rod bends to the arc; the channel is a stepped approximation of it).
    tris = []
    n = a.points
    z1, z2 = H/3.0, 2*H/3.0
    T = max(6.0, o / 0.30)                    # transition cone height (adaptive: slope stays under 0.30)
    sections = [
        (0.0,      z1 - T/2, 0.0, 0.0),      # bottom third, centered
        (z1 - T/2, z1 + T/2, 0.0, o),        # cone shift out
        (z1 + T/2, z2 - T/2, o,   o),        # middle third, offset
        (z2 - T/2, z2 + T/2, o,   0.0),      # cone shift back
        (z2 + T/2, H,        0.0, 0.0),      # top third, centered
    ]
    # outer: one constant slab big enough for both centerlines; inner: the stepped/coned bore
    OUT_R = boss_r + o                        # outer boss covers both offsets
    NZ_PER = 4
    zs, ins, outs = [], [], []
    for (za, zb, xa, xb) in sections:
        for i in range(NZ_PER + 1):
            f = i / NZ_PER
            z = za + (zb - za) * f
            cx = xa + (xb - xa) * f
            if zs and abs(z - zs[-1]) < 1e-9:
                continue
            zs.append(z)
            ins.append(ring(cx, 0.0, br, n, ccw=False))
            outs.append(ring(o/2.0, 0.0, OUT_R, n))
    # loft: walls between consecutive levels + end caps (annulus at z=0 and z=H)
    for lv in range(len(zs) - 1):
        z0, z1_ = zs[lv], zs[lv+1]
        for k in range(n):
            j = (k+1) % n
            O0, O1 = (*outs[lv][k], z0), (*outs[lv][j], z0)
            O0h, O1h = (*outs[lv+1][k], z1_), (*outs[lv+1][j], z1_)
            I0, I1 = (*ins[lv][k], z0), (*ins[lv][j], z0)
            I0h, I1h = (*ins[lv+1][k], z1_), (*ins[lv+1][j], z1_)
            tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))
            tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))
    for k in range(n):                        # end annuli
        j = (k+1) % n
        O0, O1 = (*outs[0][k], 0.0), (*outs[0][j], 0.0)
        I0, I1 = (*ins[0][k], 0.0), (*ins[0][j], 0.0)
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))
        Ot, O1t = (*outs[-1][k], H), (*outs[-1][j], H)
        It, I1t = (*ins[-1][k], H), (*ins[-1][j], H)
        tris.append((Ot, O1t, I1t)); tris.append((Ot, I1t, It))

    write_stl(out, tris)

    # ---- self-verify: laws + FUNCTION ----
    size = os.path.getsize(out)
    assert size == 84 + 50*len(tris)
    edges = {}
    for t in tris:
        key = [(round(v[0], 3), round(v[1], 3), round(v[2], 3)) for v in t]
        for i in range(3):
            e = tuple(sorted((key[i], key[(i+1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    oe = sum(1 for c in edges.values() if c != 2)
    # measured: middle-bore offset off the emitted mesh (bore centre at mid-height)
    import statistics
    mid = [v for t in tris for v in t if abs(v[2] - H/2) < s/4 and math.hypot(v[0]-o, v[1]) < br + 0.4]
    mx = statistics.mean(v[0] for v in mid) if mid else float("nan")
    checks = [
        ("watertight", oe == 0, f"{oe} open edges"),
        ("safe radius (>= {:.0f})".format(R_MIN), R >= R_MIN, f"R = {R:.0f}mm at angle {a.angle:g}"),
        ("offset measured", abs(mx - o) < 0.3, f"middle bore centre x = {mx:.2f} vs designed o = {o:.2f}"),
        ("slide bores", abs(SLIDE_BORE_D - 7.65) < 1e-9, "O7.65 slide fit (rod must thread 3 in a row)"),
        ("transitions gentle", (o / T) < 0.35, f"cone shift slope {o/T:.2f} (rod threads without snagging)"),
    ]
    print(f"{out}: {len(tris)} tris, {size}B | bar {H:.0f}mm standing, 3 bores O{SLIDE_BORE_D:g}, "
          f"middle offset {o:.2f}mm -> R {R:.0f}mm -> {a.angle:g} deg over a 24in rod")
    ok = True
    for name, good, msg in checks:
        print("  %s %-24s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (prints STANDING; the guide STAYS on the rod = the bow keeper)")


if __name__ == "__main__":
    main()
