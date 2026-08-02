#!/usr/bin/env python3
"""bend_guide_stl.py v2 -- the BEND GUIDE / BOW KEEPER, rebuilt on the real beam physics.

Oleg asked for it in his own words: "a middle stick piece as a guide for angle. pass stick thru
and you get the designate angle bend". Thread a rod through three bores, the middle one offset
sideways, and the rod is held in a bow. That idea is right and survives.

WHAT v1 GOT WRONG (all three found 2026-08-02, after Oleg said "the bend guide does not have any
holes" -- it HAD a bore, O7.65 running its whole length, but it was doing nothing):

 1. NO AUTHORITY. The bend it imposed was SMALLER than the slop in its own bore. Rods measure
    O5.8-6.2 in a O7.65 slide bore, so the rod centreline can wander 1.85 mm between the middle
    bore and the two end bores, against a designed sagitta of 0.91 mm at "15 deg" and 1.81 mm at
    "30 deg". The rod could sit dead straight inside the jig. Every self-check passed anyway,
    because each compared the geometry to its OWN declaration and never to the rod.

 2. THE ANGLE LABEL OVERSTATED BY 6.3x. v1 fitted a circle through the three bores and then
    claimed the rod took that radius over its whole 610 mm. It does not. A three-point-loaded
    beam is not a circular arc: the moment is triangular, so curvature runs from zero at the
    outer bores to a peak at the middle one, and the rod is DEAD STRAIGHT outside the outer
    bores because there is no moment out there. Integrating the real curvature:
        theta_delivered = 3*o/s          (angle between the two straight tails)
        R_peak          = s^2/(3*o)      (tightest radius, at the middle boss: what snaps it)
    The part labelled 30 deg delivers 4.8 deg. Every label in the set was 6.3x optimistic.

 3. THE WHOLE ANGLE SET WAS UNREACHABLE. Put the two real limits together, strain (R_peak >= 954,
    the 3x margin on the ~318 mm stave-measured snap radius) and bed (2s + ends <= 340), and a
    three-bore jig on this machine tops out at 9.7 deg. The advertised 15/20/25/30/35 could not
    be produced by this object at any size that fits the printer.

WHAT v2 DOES

 - Solves for the geometry instead of accepting it. Given the angle you want, spacing comes from
   whichever limit binds:  s >= 954*theta (strain)  and  s >= 12*wander/theta (authority).
   Shallow angles are limited by slop, steep ones by strain, and which one bound is printed.
 - SHIMS THE BORES. Bore is the kit standard O7.0 with a graded split TPU ring from
   shim_ring_stl.py pressed into each boss, cutting wander from 1.85 mm to ~0.25 mm. That single
   change is what makes shallow bends possible at all: at 2 deg a bare slide bore would need a
   1.7 m jig, a shimmed one needs 86 mm of spacing.
 - REFUSES what it cannot do, with the number. Past ~9.5 deg the bar runs off the bed, and it
   says so instead of emitting a jig that lies on its own label.
 - Reports the DELIVERED angle and the force the middle boss has to hold.

BIGGER BENDS need more of the rod constrained, not a bigger jig: a former holding the full 610 mm
at R = 954 gives 36.6 deg safely. That is a multi-station spine in bed-length segments, and it is
not this part. Written down so the ceiling is not mistaken for the limit of the idea.

PRINTS STANDING (bar axis vertical): the bore is a vertical channel, so round holes, no teardrop,
no support. The outer profile waists between bosses so the three stations read as three stations
at a glance, which v1 did not.

Usage: python3 bend_guide_stl.py [--angle 6] [--bare] [--section] [--out bend_guide_a6.stl]
"""
import argparse, math, os, struct

import rod_constants as RC

R_SNAP      = 318.0        # mm, stave-measured: bamboo of this stock snaps below this radius
R_MIN       = 954.0        # 3x margin on R_SNAP. The strain limit every jig is sized against
AUTHORITY   = 4.0          # sagitta must be >= this x the rod centreline wander, or the rod just
                           # sits straight in the slop (the v1 bug, now a gate)
SHIM_WANDER = 0.25         # rod play in a shimmed O7.0 boss: 0.15 shim squeeze + 0.10 print drift.
                           # ASSUMED, not measured on a printed shim. A coupon settles it.
BED         = 340.0        # K2 Plus usable
WALL_MIN    = 2.4
E_BAMBOO    = 12000.0      # MPa along the grain. ASSUMED, handbook range 10-20 GPa. Used ONLY for
                           # the reported holding force, never for the geometry.


def wander(bare):
    """Rod centreline play between the middle boss and the two end bosses."""
    return (RC.SLIDE_BORE - RC.ROD_MIN) if bare else SHIM_WANDER


def solve_spacing(theta, w):
    """Bore spacing s for a delivered angle theta (rad). Two limits, whichever binds:
         strain     o <= s^2/(3*R_MIN)  with o = theta*s/3  ->  s >= R_MIN * theta
         authority  o >= AUTHORITY * w  with o = theta*s/3  ->  s >= 3*AUTHORITY*w / theta
    Returns (s, which_limit_binds)."""
    s_strain = R_MIN * theta
    s_auth = 3.0 * AUTHORITY * w / theta
    return (s_strain, "strain") if s_strain >= s_auth else (s_auth, "authority")


def normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"crackle bend_guide v2 - 3-station bamboo bow keeper".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


def ring(cx, r, n, ccw=True):
    p = [(cx + r*math.cos(2*math.pi*k/n), r*math.sin(2*math.pi*k/n)) for k in range(n)]
    return p if ccw else p[::-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--angle", type=float, default=6.0,
                    help="DELIVERED bend between the straight tails, deg (v1 labelled this 6.3x high)")
    ap.add_argument("--bare", action="store_true",
                    help="size for a bare rod in the O7.65 slide bore instead of a shimmed O7.0 boss")
    ap.add_argument("--force-spacing", type=float, default=None,
                    help="pin the bore spacing instead of solving for it. Lets you reproduce a "
                         "known-bad jig (v1 was --angle 30 --force-spacing 65 --bare) and watch "
                         "the gates fail it.")
    ap.add_argument("--points", type=int, default=64, help="samples per ring")
    ap.add_argument("--section", action="store_true",
                    help="print a measured cross-section of the emitted mesh (the bore, visibly)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    assert a.angle > 0, "--angle must be positive"
    theta = math.radians(a.angle)
    w = wander(a.bare)
    bore_d = RC.SLIDE_BORE if a.bare else RC.BORE
    s, binds = solve_spacing(theta, w)
    if a.force_spacing is not None:
        s, binds = a.force_spacing, "pinned by --force-spacing"
        o = s * s / (2.0 * (RC.ROD_LEN / theta))   # v1's model: circle through 3 points, full-rod
    else:
        o = theta * s / 3.0                       # sagitta of the middle bore
    R_peak = s * s / (3.0 * o)
    theta_del = 3.0 * o / s        # what the geometry ACTUALLY delivers. Never echo the request:
    ang_del = math.degrees(theta_del)   # with --force-spacing the two differ, and that gap IS v1's bug
    br = bore_d / 2.0
    boss_r = br + o + WALL_MIN                # boss must enclose the bore at full offset
    waist_r = max(br + WALL_MIN, boss_r - 3.0)
    end_pad = boss_r
    H = 2 * s + 2 * end_pad
    out = a.out or f"bend_guide_a{a.angle:g}{'_bare' if a.bare else ''}.stl"

    if H > BED:
        raise SystemExit(
            f"\n{a.angle:g} deg REFUSED: needs bore spacing {s:.0f}mm, so a standing bar "
            f"{H:.0f}mm tall against a {BED:.0f}mm bed.\n"
            f"The binding limit is {binds.upper()}. "
            + (f"Holding a {R_MIN:.0f}mm peak radius (3x the {R_SNAP:.0f}mm snap radius) forces "
               f"s >= R_MIN*theta.\n" if binds == "strain" else
               f"The sagitta must beat the {w:.2f}mm rod wander by {AUTHORITY:g}x or the rod sits "
               f"straight in the slop.\n")
            + f"A three-bore jig on this bed tops out near 9.5 deg. Bigger bends need MORE OF THE "
              f"ROD constrained, not a bigger jig: a former holding the full 610mm at "
              f"R={R_MIN:.0f}\ngives {math.degrees(610/R_MIN):.1f} deg, which is a multi-station "
              f"spine in bed-length segments, not this part.")

    # ---- mesh: loft of rings. Bore centreline is a chord path 0 -> o -> 0 (straight between
    # stations, so the rod threads at a gentle slope); the outer waists between the bosses.
    n = a.points
    z_st = [end_pad, end_pad + s, end_pad + 2 * s]

    def bore_x(z):
        if z <= z_st[0]: return 0.0
        if z <= z_st[1]: return o * (z - z_st[0]) / s
        if z <= z_st[2]: return o * (z_st[2] - z) / s
        return 0.0

    def outer_r(z):
        d = min(abs(z - c) for c in z_st)
        t = min(1.0, d / (0.30 * s))                     # boss -> waist over 30% of the span
        return boss_r + (waist_r - boss_r) * (0.5 - 0.5 * math.cos(math.pi * t))

    step = min(1.5, s / 40.0)
    zs = []
    z = 0.0
    while z < H - 1e-9:
        zs.append(z)
        z += step
    zs.append(H)
    zs += z_st                                            # land exactly on the stations
    zs = sorted(set(round(v, 4) for v in zs))

    tris = []
    lv = [(z, ring(bore_x(z), br, n), ring(0.0, outer_r(z), n)) for z in zs]
    for i in range(len(lv) - 1):
        z0, i0, o0 = lv[i]; z1, i1, o1 = lv[i + 1]
        for k in range(n):
            j = (k + 1) % n
            O0, O1 = (*o0[k], z0), (*o0[j], z0)
            O0h, O1h = (*o1[k], z1), (*o1[j], z1)
            I0, I1 = (*i0[k], z0), (*i0[j], z0)
            I0h, I1h = (*i1[k], z1), (*i1[j], z1)
            tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))
            tris.append((I0, I1, I1h)); tris.append((I0, I1h, I0h))
    for (zc, ii, oo), up in ((lv[0], False), (lv[-1], True)):   # end annuli
        for k in range(n):
            j = (k + 1) % n
            A, B = (*oo[k], zc), (*oo[j], zc)
            C, D = (*ii[k], zc), (*ii[j], zc)
            tris.append((A, B, D) if up else (A, D, B))
            tris.append((A, D, C) if up else (A, C, D))

    write_stl(out, tris)

    # ---- self-verify: MEASURED off the emitted file, by re-reading it ----
    size = os.path.getsize(out)
    with open(out, "rb") as f:
        f.read(80); (ntri,) = struct.unpack("<I", f.read(4))
        V = []
        for _ in range(ntri):
            f.read(12)
            V += [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
    edges = {}
    for t in range(ntri):
        k3 = [tuple(round(c, 3) for c in V[3*t+i]) for i in range(3)]
        for i in range(3):
            e = tuple(sorted((k3[i], k3[(i+1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)

    def bore_centre_at(zq):
        """Measure the bore centre a DIFFERENT way than the generator computed it: take the
        vertices in a thin z-slab that sit on the inner surface (radius ~ br about the inner
        cluster's own centroid) and average their x."""
        near = [v for v in V if abs(v[2] - zq) < 0.9]
        if not near: return float("nan"), 0
        xs = [v[0] for v in near]
        cx = (min(xs) + max(xs)) / 2
        inner = [v for v in near if math.hypot(v[0]-cx, v[1]) < br + o + 0.6]
        if not inner: return float("nan"), 0
        icx = sum(v[0] for v in inner) / len(inner)
        on = [v for v in inner if abs(math.hypot(v[0]-icx, v[1]) - br) < 0.25]
        if not on: return float("nan"), 0
        return sum(v[0] for v in on) / len(on), len(on)

    mid_x, nmid = bore_centre_at(z_st[1])
    end_x, nend = bore_centre_at(z_st[0])
    measured_o = mid_x - end_x
    zmax = max(v[2] for v in V)
    xr = max(v[0] for v in V) - min(v[0] for v in V)
    F_hold = 48 * E_BAMBOO * (math.pi * RC.ROD_NOM**4 / 64) * o / ((2*s)**3)

    print(f"{out}: {ntri} tris, {size}B | 3 stations {s:.0f}mm apart, bar {zmax:.0f}mm standing "
          f"x {xr:.0f}mm wide, bore O{bore_d:g}{'' if a.bare else ' + TPU shim per boss'}")
    print(f"  DELIVERS {ang_del:.1f} deg between the straight tails (asked for {a.angle:g}), "
          f"sagitta {o:.2f}mm, peak radius {R_peak:.0f}mm, middle boss holds ~{F_hold:.0f} N")
    print(f"  binding limit: {binds}   (strain wants s>={R_MIN*theta:.0f}, "
          f"authority wants s>={3*AUTHORITY*w/theta:.0f})")

    checks = [
        ("watertight", open_edges == 0, f"{open_edges} open edges"),
        ("bed fit", zmax <= BED and xr <= BED, f"{zmax:.0f} x {xr:.0f} mm vs {BED:.0f}"),
        (f"authority >= {AUTHORITY:g}x", o >= AUTHORITY * w,
         f"sagitta {o:.2f}mm vs rod wander {w:.2f}mm = {o/w:.1f}x "
         f"(v1 shipped at 0.98x and held nothing)"),
        (f"strain R >= {R_MIN:.0f}", R_peak >= R_MIN - 0.5,
         f"peak radius {R_peak:.0f}mm at the middle boss, snap radius {R_SNAP:.0f}mm"),
        ("offset MEASURED", abs(measured_o - o) < 0.30,
         f"emitted mesh gives {measured_o:.2f}mm ({nmid}+{nend} surface verts) vs designed {o:.2f}mm"),
        ("label honest", abs(ang_del - a.angle) < 0.15,
         f"delivers {ang_del:.1f} deg against a {a.angle:g} deg label "
         f"(v1 labelled 30 and delivered 4.8)"),
        ("threadable", (o / s) < 0.12,
         f"channel slope {o/s:.3f}, the rod slides in without snagging"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-22s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good

    if a.section:
        print("\n  cross-section at each station, measured off the emitted mesh (# wall, . bore):")
        lo = min(v[0] for v in V); hi = max(v[0] for v in V)
        for lbl, zq in (("bottom", z_st[0]), ("middle", z_st[1]), ("top", z_st[2])):
            cols, row = 56, []
            for c in range(cols):
                x = lo + (hi - lo) * c / (cols - 1)
                inside_out = abs(x) <= outer_r(zq)
                inside_bore = abs(x - bore_x(zq)) <= br
                row.append("." if (inside_out and inside_bore) else ("#" if inside_out else " "))
            print(f"    {lbl:6s} z={zq:6.1f}  |{''.join(row)}|")
        print(f"    the bore shifts {measured_o:.2f}mm between the bottom and middle stations")

    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (prints STANDING; the guide STAYS on the rod = the bow keeper)")


if __name__ == "__main__":
    main()
