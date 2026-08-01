#!/usr/bin/env python3
"""marble_common — the ONE connection standard + mesh/STL plumbing for the marble-run kit.

Every kit part couples the same way (defined here, used everywhere):
  TOP    = female SOCKET, surface Ø56, 15 mm deep  — slips OVER a Ø55 male below it
  BOTTOM = male SPIGOT,  surface Ø55, 15 mm long  — slips INTO the Ø56 socket of the next part
So the chain is: funnel spout (Ø55) -> part socket -> part spigot -> next socket, daisy-chained.
Ø56 over Ø55 leaves 0.5 mm on the surface model; vase-printed (Creality empirics: hole ≈ model
−0.25) that lands as a snug slip fit. Tune --socket per printer if needed.

Marbles are ~Ø16; free path anywhere a marble must pass is ≥ Ø22.

Meshes are OPEN single surfaces (funnel_stl.py style): a grid of rings, single-valued r(θ, z),
so slicer VASE mode prints them as one continuous wall. Z-monotonic by construction.
"""
import math, os, struct

# ---- the kit standard (surface dimensions, mm) ----
SOCKET_D = 56.0     # female socket diameter, top of every part
SPIGOT_D = 55.0     # male spigot diameter, bottom of every part (matches the funnel spout)
COUPLE_L = 15.0     # socket depth / spigot length = friction-fit overlap
MARBLE_D = 16.0     # standard marble
BORE_D   = 24.0     # default free marble path (marble + 8 mm of air)
CONE_SLOPE = 1.0    # max |dr/dz| for transition cones (45° from vertical)


def cone_h(r0, r1, slope=CONE_SLOPE):
    """Height a transition cone needs to stay within the print-safe slope."""
    return abs(r1 - r0) / slope


def rev_rings(profile, n_pts):
    """profile = [(z, r), ...] -> ring grid rows [(z, [r]*n)] (surface of revolution)."""
    return [(z, [r] * n_pts) for z, r in profile]


def grid_tris(rows, n_pts, close=True):
    """rows = [(z, [r_0..r_{n-1}]), ...] bottom->top; quads between rings -> triangles.
    Same winding as funnel_stl.py."""
    def pt(z, radii, k):
        th = 2 * math.pi * k / n_pts
        return (radii[k] * math.cos(th), radii[k] * math.sin(th), z)
    tris = []
    rng = n_pts if close else n_pts - 1
    for i in range(len(rows) - 1):
        z0, r0 = rows[i]; z1, r1 = rows[i + 1]
        for k in range(rng):
            k1 = (k + 1) % n_pts
            p00 = pt(z0, r0, k); p01 = pt(z0, r0, k1)
            p10 = pt(z1, r1, k); p11 = pt(z1, r1, k1)
            tris.append((p00, p10, p11)); tris.append((p00, p11, p01))
    return tris


def disc_tris(z, r, n_pts, up=False):
    """Closed floor cap (for the catch cup): triangle fan at height z."""
    tris = []
    c = (0.0, 0.0, z)
    for k in range(n_pts):
        th0 = 2 * math.pi * k / n_pts; th1 = 2 * math.pi * (k + 1) / n_pts
        a = (r * math.cos(th0), r * math.sin(th0), z)
        b = (r * math.cos(th1), r * math.sin(th1), z)
        tris.append((c, a, b) if up else (c, b, a))
    return tris


def write_stl(path, tris):
    """Binary STL, funnel_stl.py style."""
    with open(path, "wb") as f:
        f.write(b"\0" * 80); f.write(struct.pack("<I", len(tris)))
        for t in tris:
            ux, uy, uz = (t[1][0]-t[0][0], t[1][1]-t[0][1], t[1][2]-t[0][2])
            vx, vy, vz = (t[2][0]-t[0][0], t[2][1]-t[0][1], t[2][2]-t[0][2])
            nx, ny, nz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
            m = math.hypot(nx, ny, nz) or 1.0
            f.write(struct.pack("<3f", nx/m, ny/m, nz/m))
            for p in t: f.write(struct.pack("<3f", *p))
            f.write(b"\0\0")


def verify_stl(path):
    """Read the FILE back (different route than the writer) and measure it:
    size == 84+50n, triangle count, bounds, degenerate (zero-area) count,
    max wall lean from vertical (printability)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        assert size == 84 + 50 * n, f"{path}: size {size} != 84+50*{n}"
        lo = [1e30] * 3; hi = [-1e30] * 3
        degen = 0; max_lean = 0.0; flat = 0
        for _ in range(n):
            f.read(12)
            vs = [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
            for v in vs:
                for j in range(3):
                    lo[j] = min(lo[j], v[j]); hi[j] = max(hi[j], v[j])
            ux, uy, uz = (vs[1][0]-vs[0][0], vs[1][1]-vs[0][1], vs[1][2]-vs[0][2])
            vx, vy, vz = (vs[2][0]-vs[0][0], vs[2][1]-vs[0][1], vs[2][2]-vs[0][2])
            cx, cy, cz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
            a2 = math.hypot(cx, cy, cz)
            if a2 < 1e-9:
                degen += 1
            else:
                lean = math.degrees(math.asin(min(1.0, abs(cz) / a2)))
                if lean > 89.5:
                    flat += 1          # horizontal face (e.g. a floor disc on the bed)
                else:
                    max_lean = max(max_lean, lean)
    return dict(size=size, tris=n, lo=lo, hi=hi, degen=degen, max_lean=max_lean, flat=flat)


def report(path, v, note=""):
    print(f"{path}: {v['tris']} triangles, {v['size']} bytes (=84+50n OK), "
          f"{v['degen']} degenerate, bounds "
          f"x[{v['lo'][0]:.1f},{v['hi'][0]:.1f}] y[{v['lo'][1]:.1f},{v['hi'][1]:.1f}] "
          f"z[{v['lo'][2]:.1f},{v['hi'][2]:.1f}] mm, max wall lean {v['max_lean']:.0f}° from vertical"
          + (f" (+{v['flat']} flat floor tris on the bed)" if v.get('flat') else ""))
    print(f"  coupling: socket Ø{SOCKET_D:g}x{COUPLE_L:g} top / spigot Ø{SPIGOT_D:g}x{COUPLE_L:g} "
          f"bottom — VASE mode, single wall{('. ' + note) if note else ''}")
