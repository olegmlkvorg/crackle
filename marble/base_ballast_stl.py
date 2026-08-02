#!/usr/bin/env python3
"""BALLAST BASE STL -- the piece that lets a printed tower stand up, and the reason it is a tray.

Oleg asked for "a bunch of different base pieces to assemble a structure". The first honest answer
is that a WIDE PLATE DOES NOT WORK, and the arithmetic says so before any plastic is spent.

THE TIP-OVER MATH (measured tower, not a guessed one). A spiral chute is a single 1.2mm vase wall:
surface area measured off the emitted mesh is 315.2 cm2, so 46.9 g of PLA per 235.3mm segment.
Tip a tower about the rim of its base and the restoring moment is M*g*b (M total mass, b the half
footprint) against an overturning moment F*H (a sideways nudge F applied at height H). So

    b >= F * H / (M * g)

For an unballasted tower this is hopeless, and the hopelessness does not depend on how tall it is:
mass grows with height, so H/M is constant. A 1 N nudge (about 100 g of hand) needs b = 256mm, a
half-metre plate, for a tower of ANY height. 2 N needs a metre.

Ballast fixes it because it adds M without adding H. 500 g of dry sand in the tray brings the same
1 N nudge down to b = 81mm, a 162mm base. That is why this part is a TRAY and not a disc, and it
is why the gift-shop line already mixes filament with sand and gypsum.

FOOTPRINT IS DERIVED, NOT PICKED. Give it the tower it must hold and the nudge it must survive and
it solves for the radius, then sizes the tray depth to actually hold that much sand. The FUNCTION
check fails a base too small for the tower it claims to support, and --nudge lets you watch it fail.

SHAPE: a lathe, one closed profile revolved, so it comes out watertight. Bed, up the outer wall,
over the rim, down the inside, across the tray floor, up the central boss, then the BOND v2.1
female socket bored down into it. Nothing faces downward except the bed, so it prints support free
standing exactly as modelled. It is NOT a vase part: a tray with a boss in it has two walls at the
same height, which single-wall vase mode cannot do, and pretending otherwise is how this project
shipped unprintable parts twice.

Usage: python3 base_ballast_stl.py [--segments 2] [--nudge 1.0] [--ballast 500] [--sockets 1]
"""
import argparse, math, os, struct

import marble_common as mc

CHUTE_G     = 46.9      # g per chute segment. MEASURED: 315.2 cm2 emitted surface x 1.2 wall x 1.24
CHUTE_H     = 235.3     # mm per chute segment, measured off the emitted mesh
SAND_RHO    = 1.6e-3    # g/mm3, dry sand loose poured. ASSUMED, handbook 1.4-1.7. Weigh it once.
PLA_RHO     = 1.24e-3   # g/mm3
G           = 9.81
WALL        = 2.0       # tray wall. Thicker than a vase bead because this one takes a knock
FLOOR       = 2.4
SAFETY      = 1.25      # on the derived footprint
TRAY_MIN    = 8.0       # mm of sand depth below which it slops out when the base is moved


def solve_radius(nudge_N, tower_h, tower_g, ballast_g):
    """Half footprint b that survives a sideways nudge at the top of the tower."""
    M = (tower_g + ballast_g) * 1e-3
    return nudge_N * tower_h * 1e-3 / (M * G) * 1e3 * SAFETY


def lathe(profile, n, dx=0.0, dy=0.0):
    """Revolve a CLOSED (r, z) polygon into a watertight solid. profile runs anticlockwise in the
    (r, z) half plane; r may double back, which is the whole point (a tray has two walls)."""
    tris = []
    m = len(profile)
    for i in range(m):
        r0, z0 = profile[i]
        r1, z1 = profile[(i + 1) % m]
        for k in range(n):
            a0 = 2 * math.pi * k / n
            a1 = 2 * math.pi * (k + 1) / n
            p00 = (dx + r0*math.cos(a0), dy + r0*math.sin(a0), z0)
            p01 = (dx + r0*math.cos(a1), dy + r0*math.sin(a1), z0)
            p10 = (dx + r1*math.cos(a0), dy + r1*math.sin(a0), z1)
            p11 = (dx + r1*math.cos(a1), dy + r1*math.sin(a1), z1)
            if r0 > 1e-9:
                tris.append((p00, p01, p11))
            if r1 > 1e-9:
                tris.append((p00, p11, p10))
    return tris


def normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"crackle base_ballast - sand-filled tray base for a printed tower".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", type=int, default=2, help="chute segments the tower is made of")
    ap.add_argument("--nudge", type=float, default=1.0, help="sideways nudge at the top, N")
    ap.add_argument("--ballast", type=float, default=None,
                    help="sand poured into the tray, g. Default: SOLVED so the tray is deep enough "
                         "to hold it, because more sand shrinks the base which shrinks the tray.")
    ap.add_argument("--sockets", type=int, default=1, choices=(1, 2, 3),
                    help="towers this base carries, spaced on the kit structure grid")
    ap.add_argument("--radius", type=float, default=None,
                    help="pin the base radius instead of deriving it. Makes the tip-over check a "
                         "real gate: ask for a base too small and watch it fail.")
    ap.add_argument("--points", type=int, default=120)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    tower_h = a.segments * CHUTE_H
    tower_g = a.segments * CHUTE_G * a.sockets
    boss_r = mc.SOCKET_MOUTH_R + WALL
    spread0 = (a.sockets - 1) * mc.GRID_PITCH / 2

    def geometry(ballast_g):
        bb = solve_radius(a.nudge, tower_h, tower_g, ballast_g)
        RR = a.radius if a.radius is not None else max(bb, boss_r + WALL + 12.0 + 2*spread0)
        ann = math.pi * ((RR - WALL)**2 - a.sockets * boss_r**2)
        return RR, ann, ballast_g / (SAND_RHO * ann) + FLOOR

    if a.ballast is not None:
        ballast = a.ballast
    else:
        # more sand -> heavier -> smaller base -> smaller tray -> deeper for the same sand.
        # Walk up until the tray is a sane depth; it converges in a few steps.
        ballast = 200.0
        for _ in range(60):
            _, _, dep = geometry(ballast)
            if dep - FLOOR >= TRAY_MIN + 4.0:
                break
            ballast += 50.0
    a.ballast = ballast
    b = solve_radius(a.nudge, tower_h, tower_g, ballast)
    # the base must at least contain its own socket, plus the grid offset of the outer sockets
    R, annulus0, depth0 = geometry(ballast)
    out = a.out or f"base_ballast_s{a.sockets}_{a.segments}seg.stl"

    depth = depth0
    boss_h = depth + 4.0                       # boss stands proud of the sand so it stays clean
    socket_floor = boss_h - mc.COUPLE_L

    if socket_floor < FLOOR:                   # socket would cut through the floor
        boss_h = mc.COUPLE_L + FLOOR
        socket_floor = FLOOR

    def dedupe(q):
        out_ = [q[0]]                              # consecutive duplicates make zero-area tris,
        for v in q[1:]:                            # which break edge parity AND fail DEGENERATE
            if abs(v[0]-out_[-1][0]) > 1e-6 or abs(v[1]-out_[-1][1]) > 1e-6:
                out_.append(v)
        if abs(out_[0][0]-out_[-1][0]) < 1e-6 and abs(out_[0][1]-out_[-1][1]) < 1e-6:
            out_.pop()
        return out_

    def socket_boss(base_z):
        """A boss with the BOND v2.1 socket bored down into it, as its own closed lathe."""
        q = [(0.0, base_z), (boss_r, base_z), (boss_r, boss_h), (mc.SOCKET_MOUTH_R, boss_h)]
        q += [(mc.socket_r(d), socket_floor + d)
              for d in reversed([i * mc.COUPLE_L / 24 for i in range(25)])]
        q += [(0.0, socket_floor)]
        return dedupe(q)

    # ---- the tray, one closed lathe profile, anticlockwise in (r, z) ----
    if a.sockets == 1:
        prof = [(0.0, 0.0), (R, 0.0), (R, depth), (R - WALL, depth), (R - WALL, FLOOR)]
        prof += socket_boss(FLOOR)[1:]             # central boss continues the same loop
        tris = lathe(dedupe(prof), a.points)
        centres = [(0.0, 0.0)]
    else:
        # Multi socket cannot be one surface of revolution, so the tray is lathed flat and each
        # boss is its own closed solid dropped onto it. Overlapping closed bodies: every body is
        # individually watertight, which is what the slicer and the gate both need.
        prof = [(0.0, 0.0), (R, 0.0), (R, depth), (R - WALL, depth), (R - WALL, FLOOR), (0.0, FLOOR)]
        tris = lathe(dedupe(prof), a.points)
        centres = [((i - (a.sockets - 1) / 2) * mc.GRID_PITCH, 0.0) for i in range(a.sockets)]
        for cx, cy in centres:
            tris += lathe(socket_boss(0.0), a.points, cx, cy)

    write_stl(out, tris)

    # ---- self-verify: re-read the file and MEASURE it ----
    size = os.path.getsize(out)
    with open(out, "rb") as f:
        f.read(80); (n,) = struct.unpack("<I", f.read(4))
        V = []
        for _ in range(n):
            f.read(12)
            V += [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
    edges = {}
    for t in range(n):
        k3 = [tuple(round(c, 3) for c in V[3*t+i]) for i in range(3)]
        for i in range(3):
            e = tuple(sorted((k3[i], k3[(i+1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)
    meas_R = max(math.hypot(v[0], v[1]) for v in V)
    meas_H = max(v[2] for v in V)
    # socket mouth measured off the mesh: widest ring at the boss top
    cx0, cy0 = centres[0]
    top = [v for v in V if abs(v[2] - boss_h) < 0.4
           and math.hypot(v[0]-cx0, v[1]-cy0) < boss_r + 0.5]
    meas_mouth = 2 * min(math.hypot(v[0]-cx0, v[1]-cy0) for v in top) if top else float("nan")

    # what the emitted base actually survives, recomputed FROM the measured radius
    M = (tower_g + a.ballast) * 1e-3
    survives_N = M * G * (meas_R * 1e-3) / (tower_h * 1e-3)
    bare_N = (tower_g * 1e-3) * G * (meas_R * 1e-3) / (tower_h * 1e-3)

    print(f"{out}: {n} tris, {size}B | base O{2*meas_R:.0f} x {meas_H:.1f} tall, {a.sockets} socket(s), "
          f"tray holds {a.ballast:.0f} g of sand {depth - FLOOR:.0f} mm deep")
    print(f"  tower {a.segments} x chute = {tower_h:.0f} mm, {tower_g:.0f} g measured. "
          f"Ballasted it survives a {survives_N:.2f} N nudge at the top; EMPTY it survives "
          f"{bare_N:.2f} N, which is why the tray is the part.")
    vol = 0.0                                      # signed volume of the emitted mesh, not a formula
    for t in range(n):
        A, B, C = V[3*t], V[3*t+1], V[3*t+2]
        vol += (A[0]*(B[1]*C[2]-C[1]*B[2]) - A[1]*(B[0]*C[2]-C[0]*B[2])
                + A[2]*(B[0]*C[1]-C[0]*B[1])) / 6.0
    vol = abs(vol)
    print(f"  plastic {vol*PLA_RHO:.0f} g MEASURED off the mesh ({vol/1000:.0f} cm3), "
          f"so the sand is {a.ballast/(vol*PLA_RHO):.1f}x the mass of the part carrying it")

    checks = [
        ("watertight", open_edges == 0, f"{open_edges} open edges"),
        ("holds the nudge", survives_N >= a.nudge,
         f"survives {survives_N:.2f} N vs the {a.nudge:g} N it was sized for"),
        ("ballast earns it", survives_N >= 3 * bare_N,
         f"ballasted {survives_N:.2f} N vs empty {bare_N:.2f} N = {survives_N/max(bare_N,1e-9):.1f}x"),
        ("socket is kit standard", abs(meas_mouth - mc.SOCKET_MOUTH_D) < 0.4,
         f"measured mouth O{meas_mouth:.2f} vs BOND v2.1 O{mc.SOCKET_MOUTH_D:.2f}"),
        ("every socket modelled", len(centres) == a.sockets,
         f"{len(centres)} boss(es) placed on the {mc.GRID_PITCH:.1f}mm structure grid"),
        ("bed fit", 2 * meas_R <= 340, f"O{2*meas_R:.0f} vs 340 bed"),
        ("tray deep enough", depth - FLOOR >= TRAY_MIN,
         f"{depth - FLOOR:.0f} mm of sand depth (shallower than {TRAY_MIN:g} and it slops out)"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-24s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (prints STANDING as modelled, no support, fill with dry sand)")


if __name__ == "__main__":
    main()
