#!/usr/bin/env python3
"""BOND TPU RING -- a stretch band that squeezes the joint shut. Oleg: "we need tight coupling,
may be aditional tpu ring if needed for stability".

Belt and braces, and the two do different jobs. The PLA fit (marble_common) sets the geometry and
gives the click. This ring adds what printed PLA cannot: a live preload that does not care about
print drift. A vase-printed socket is one springy wall; a TPU band stretched around it pulls that
wall permanently onto the spigot, so the joint stops depending on hitting a clearance target to
within a tenth of a millimetre.

WHERE IT GRIPS. Over the LAND, the zone where the two walls run parallel and the detent lives.
Sizes come off the corrected socket path plus half a bead, because a vase wall is laid CENTRED on
the path, so the outer face is path + wall/2, not path + wall. Getting that wrong by half a bead
is the same class of error that made the coupling loose in the first place.

HOW IT GOES ON. Stretch it over the socket mouth (the widest point) and roll it down to the land.
The mouth is the strain peak, and the ring is sized so that strain stays inside what TPU takes
without yielding.

PRINTS ON THE K1C in TPU: 205 C, model fan 20, flat on the bed, no support. Two perimeters, no
infill: a band is all wall.

Usage: python3 bond_tpu_ring_stl.py [--squeeze 0.6] [--height 10] [--wall 1.6]
"""
import argparse, math, os, struct

import marble_common as mc

TPU_MAX_STRAIN = 0.35    # hoop strain the band may see going over the mouth. ASSUMED for a
                         # printed 95A TPU band, not measured. A snapped ring disproves it.
WALL_MIN = 1.2           # thinnest band that still pulls hard rather than just sitting there


def outer_face(path_r):
    """Outer face of a vase wall whose SURFACE PATH is at path_r. Half a bead out, not a whole
    one: the extrusion straddles the path."""
    return path_r + mc.LINE_W / 2.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--squeeze", type=float, default=0.6,
                    help="diametral interference on the land, mm (how hard it pulls)")
    ap.add_argument("--height", type=float, default=10.0, help="band height mm")
    ap.add_argument("--wall", type=float, default=1.6, help="band wall mm (2 x 0.8 perimeters)")
    ap.add_argument("--points", type=int, default=180)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    assert a.wall >= WALL_MIN, f"--wall under {WALL_MIN} will not pull, it will just sit there"

    land_od = 2 * outer_face(mc.socket_r(mc.LAND_H / 2))   # where it grips
    mouth_od = 2 * outer_face(mc.socket_r(mc.COUPLE_L))    # what it must stretch over to get there
    ring_id = land_od - a.squeeze
    ring_od = ring_id + 2 * a.wall
    strain_seated = (land_od - ring_id) / ring_id
    strain_mouth = (mouth_od - ring_id) / ring_id
    out = a.out or f"bond_tpu_ring_sq{int(round(a.squeeze*100)):02d}.stl"

    n = a.points
    tris = []
    ri, ro, h = ring_id / 2, ring_od / 2, a.height
    inn = [(ri*math.cos(2*math.pi*k/n), ri*math.sin(2*math.pi*k/n)) for k in range(n)]
    outr = [(ro*math.cos(2*math.pi*k/n), ro*math.sin(2*math.pi*k/n)) for k in range(n)]
    for k in range(n):
        j = (k + 1) % n
        O0, O1 = (*outr[k], 0.0), (*outr[j], 0.0)
        O0h, O1h = (*outr[k], h), (*outr[j], h)
        I0, I1 = (*inn[k], 0.0), (*inn[j], 0.0)
        I0h, I1h = (*inn[k], h), (*inn[j], h)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))

    def nrm(p, q, r):
        u = (q[0]-p[0], q[1]-p[1], q[2]-p[2]); v = (r[0]-p[0], r[1]-p[1], r[2]-p[2])
        c = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        m = math.hypot(*c) or 1.0
        return (c[0]/m, c[1]/m, c[2]/m)

    with open(out, "wb") as f:
        f.write(b"crackle bond_tpu_ring - stretch band preloading the marble joint".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", *nrm(*t)))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))

    # ---- self-verify off the emitted file ----
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
    rr = [math.hypot(v[0], v[1]) for v in V]
    meas_id, meas_od = 2 * min(rr), 2 * max(rr)
    meas_h = max(v[2] for v in V)

    print(f"{out}: {ntri} tris | band O{meas_id:.2f} inner x O{meas_od:.2f} outer x {meas_h:.0f} mm, "
          f"wall {a.wall:g}")
    print(f"  socket outer face: land O{land_od:.2f}, mouth O{mouth_od:.2f} "
          f"(path + half a {mc.LINE_W:g} bead, because the wall straddles the path)")
    print(f"  seated strain {strain_seated*100:.1f}%, peak strain crossing the mouth "
          f"{strain_mouth*100:.1f}%")

    checks = [
        ("watertight", open_edges == 0, f"{open_edges} open edges"),
        ("measured ID", abs(meas_id - ring_id) < 0.02,
         f"emitted O{meas_id:.2f} vs designed O{ring_id:.2f}"),
        ("it actually squeezes", a.squeeze >= 0.3,
         f"{a.squeeze:g} mm diametral interference on the land"),
        ("survives the mouth", strain_mouth <= TPU_MAX_STRAIN,
         f"{strain_mouth*100:.1f}% hoop strain going over the mouth, assumed limit "
         f"{TPU_MAX_STRAIN*100:.0f}%"),
        ("covers the detent", a.height >= mc.BUMP_Z + mc.BUMP_W / 2,
         f"{a.height:g} mm tall vs a detent centred {mc.BUMP_Z:g} mm up"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-22s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (K1C, TPU 205 C, model fan 20, flat, 2 perimeters, no infill)")


if __name__ == "__main__":
    main()
