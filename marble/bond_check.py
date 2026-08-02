#!/usr/bin/env python3
"""bond_check.py — CROSS-PART gate for the kit's BOND v2.1 coupling, measured off the EMITTED meshes.

House discipline: the generator's summary line is not the file. This reads the binary STLs back,
extracts the male (bottom COUPLE_L) and female (top COUPLE_L) ring profiles, and measures every
male x female pairing the kit can form. ACCEPTANCE IS DYNAMIC (the v2 lesson: every static
check here was green while the measured pull-out force was zero — on the old 7 deg cone,
withdrawal opened clearance faster than the bump chased the groove shoulder):

    WITHDRAW  mc.withdrawal_sweep on the MEASURED profiles: slide the male out 0..8 mm in
              0.25 mm steps, max radial face interference at each step; the peak is the snap
              you must overcome to separate — REQUIRED >= 0.45 mm
    REST      interference at nominal full seat <= 0.05 mm (it seats calmly, no fight)
    LAND      face clearance constant inside [0.10, 0.15] over the bulge-free land (parallel
              paths: early withdrawal must not open clearance)
    ENTRY     mouth clearance generous, 0.40-0.60
    TAPER     clearance non-increasing mouth -> land over the ramp zone
    DETENT    bump centre lands in the groove centre at full seat (within 0.5 mm)
    GROOVE>BUMP  the groove is deeper than the bump (it can nest, with slack)
    DEPTH     detent centre >= 10 mm below the female rim
    RING-CLEAR the star ring (OPTIONAL decoration, star_ring_stl.py) wedges RING_REACH mm below
              the rim on the mouth cone; the groove bulge must stay >= 1 mm below its reach
    SLOPE     max profile slope on both bond surfaces -> lean <= 55 deg from vertical (vase law)

Any FAIL quarantines the implicated STLs to *.FAILED and exits 1.

Usage: python3 bond_check.py [drop_tube.stl spiral_chute.stl catch_cup.stl]
"""
import math, os, struct, sys

import marble_common as mc
import star_ring_stl as sr

MALES   = ("drop_tube.stl", "spiral_chute.stl")            # parts with a spigot (bottom)
FEMALES = ("drop_tube.stl", "spiral_chute.stl", "catch_cup.stl")  # parts with a socket (top)
SEAT_LO, SEAT_HI = 0.10, 0.15      # required face clearance band over the land
ENTRY_LO, ENTRY_HI = 0.40, 0.60    # required face clearance band at the mouth
ALIGN_TOL = 0.5                    # bump centre vs groove centre at full seat
RING_MARGIN = 1.0                  # groove top must stay this far below the ring's reach
BASE_A, BASE_B = 0.5, 7.5          # baseline anchors bracketing the detent (land is flat there)


def read_verts(path):
    verts = []
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        for _ in range(n):
            f.read(12)
            for _ in range(3):
                verts.append(struct.unpack("<3f", f.read(12)))
            f.read(2)
    return verts


def rings(verts, z0, z1):
    """Ring profile in [z0, z1]: sorted [(z, r_mean)]; asserts each ring is round (revolution)."""
    by_z = {}
    for x, y, z in verts:
        if z0 - 1e-4 <= z <= z1 + 1e-4:
            by_z.setdefault(round(z, 5), []).append(math.hypot(x, y))
    prof = []
    for z in sorted(by_z):
        rs = by_z[z]
        assert max(rs) - min(rs) < 0.02, f"ring z={z}: not a revolution (spread {max(rs)-min(rs):.3f})"
        prof.append((z, sum(rs) / len(rs)))
    return prof


def interp(prof, z):
    for i in range(1, len(prof)):
        if prof[i][0] >= z - 1e-9:
            (za, ra), (zb, rb) = prof[i - 1], prof[i]
            if zb - za < 1e-12:
                return rb
            t = (z - za) / (zb - za)
            return ra + (rb - ra) * max(0.0, min(1.0, t))
    return prof[-1][1]


def crest(prof, lo, hi):
    """Detent bulge vs the local cone: deviation from the line through the profile at lo and hi.
    Returns (centre_z, height, top_edge_z) measured on a 0.05 mm grid."""
    ra, rb = interp(prof, lo), interp(prof, hi)
    best_z, best_h, top = lo, 0.0, lo
    n = int((hi - lo) / 0.05)
    for i in range(n + 1):
        z = lo + (hi - lo) * i / n
        dev = interp(prof, z) - (ra + (rb - ra) * (z - lo) / (hi - lo))
        if dev > best_h:
            best_h, best_z = dev, z
        if dev > 0.05:
            top = z
    return best_z, best_h, top


def max_lean(prof):
    s = max(abs(rb - ra) / (zb - za) for (za, ra), (zb, rb) in zip(prof, prof[1:]) if zb - za > 1e-6)
    return math.degrees(math.atan(s))


def main():
    files = sys.argv[1:] or list(dict.fromkeys(MALES + FEMALES))
    verts = {os.path.basename(p): (p, read_verts(p)) for p in files}
    fails, bad = [], set()

    def check(name, ok, msg, who):
        print("  %s %-12s %s" % ("PASS" if ok else "FAIL", name, msg))
        if not ok:
            fails.append(name)
            bad.update(who)

    males, females = {}, {}
    for base, (path, vs) in verts.items():
        zmax = max(v[2] for v in vs)
        if base in MALES:
            males[base] = rings(vs, 0.0, mc.COUPLE_L)
        if base in FEMALES:
            females[base] = [(z - (zmax - mc.COUPLE_L), r)
                             for z, r in rings(vs, zmax - mc.COUPLE_L, zmax)]

    # per-surface: slope law + detent geometry
    print("== surfaces ==")
    for base, prof in list(males.items()) + [(b + " (socket)", p) for b, p in females.items()]:
        lean = max_lean(prof)
        check("SLOPE", lean <= 55.0, "%-28s max profile lean %.1f deg (limit 55)" % (base, lean),
              {base.split(" ")[0]})

    # every male x female pairing the kit can form
    for mb, mp in males.items():
        for fb, fp in females.items():
            print("== %s spigot -> %s socket ==" % (mb, fb))
            clear = [interp(fp, d) - interp(mp, d) - mc.LINE_W for d in range(int(mc.COUPLE_L) + 1)]
            print("  engagement d(mm)->face clearance: " +
                  " ".join("%d:%.2f" % (d, c) for d, c in enumerate(clear)))
            who = {mb, fb}
            bz, bh, _ = crest(mp, BASE_A, BASE_B)
            gz, gh, gtop = crest(fp, BASE_A, BASE_B)
            # the true friction seat: bulge-free land samples (detent lives in d ~ 1..7)
            land = [clear[0], interp(fp, 0.5) - interp(mp, 0.5) - mc.LINE_W,
                    interp(fp, 7.5) - interp(mp, 7.5) - mc.LINE_W, clear[8]]
            # DYNAMIC acceptance: the withdrawal sweep on the measured profiles
            sw = mc.withdrawal_sweep(mp, fp)
            print("  withdrawal sweep (mm out : max interference): " +
                  " ".join("%.2f:%+.2f" % c for c in sw["curve"]))
            check("WITHDRAW", sw["peak"] >= mc.SNAP_MIN,
                  "peak interference %+.3f mm at %.2f mm out (snap to separate, need >= %.2f)"
                  % (sw["peak"], sw["peak_at"], mc.SNAP_MIN), who)
            check("REST", sw["rest"] <= mc.REST_MAX,
                  "full-seat interference %+.3f mm (need <= %.2f; gravity settles %+.2f mm)"
                  % (sw["rest"], mc.REST_MAX, sw["settle"]), who)
            check("LAND", all(SEAT_LO <= c <= SEAT_HI for c in land)
                          and max(land) - min(land) <= 0.03,
                  "land clearance d={0,0.5,7.5,8}: %s (band %.2f-%.2f, parallel within 0.03)"
                  % ("/".join("%.3f" % c for c in land), SEAT_LO, SEAT_HI), who)
            check("ENTRY", ENTRY_LO <= clear[16] <= ENTRY_HI,
                  "mouth clearance %.3f (band %.2f-%.2f)" % (clear[16], ENTRY_LO, ENTRY_HI), who)
            check("TAPER", all(clear[d + 1] >= clear[d] - 1e-3 for d in range(8, 16)),
                  "clearance non-decreasing land->mouth over the ramp (d=8..16)", who)
            check("DETENT", abs(bz - gz) <= ALIGN_TOL,
                  "bump centre z=%.2f vs groove centre z=%.2f -> misalign %.2f mm (tol %.1f)"
                  % (bz, gz, abs(bz - gz), ALIGN_TOL), who)
            check("GROOVE>BUMP", gh > bh,
                  "groove %.3f deep vs bump %.3f -> in-groove slack %.3f mm (clicks, no bottoming)"
                  % (gh, bh, gh - bh + min(land)), who)
            check("DEPTH", mc.COUPLE_L - gz >= 10.0,
                  "detent centre %.1f mm below the female rim (needs >= 10)" % (mc.COUPLE_L - gz), who)
            # star ring (OPTIONAL decoration): wedges RING_REACH mm below the rim on the mouth
            # outer cone; the groove's outward bulge must stay clear of that band
            ring_reach = mc.COUPLE_L - sr.RING_REACH      # lowest d the seated ring reaches
            check("RING-CLEAR", gtop <= ring_reach - RING_MARGIN,
                  "ring wedges %.1f mm below the rim; groove top d=%.2f = %.1f mm below rim "
                  "-> %.2f mm below the ring (needs >= %.1f)"
                  % (sr.RING_REACH, gtop, mc.COUPLE_L - gtop, ring_reach - gtop, RING_MARGIN), who)

    if fails:
        for base in sorted(bad):
            path = verts[base][0]
            os.replace(path, path + ".FAILED")
            print("QUARANTINED %s -> %s.FAILED" % (path, path))
        print("FAIL bond_check: %d check(s) failed" % len(fails))
        sys.exit(1)
    print("PASS bond_check: %d male x %d female pairings, all checks green"
          % (len(males), len(females)))


if __name__ == "__main__":
    main()
