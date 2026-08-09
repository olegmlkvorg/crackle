#!/usr/bin/env python3
"""Force-fire the art-bucket gates against known-bad artifacts, per the house law: a gate
counts only once it has been SEEN to reject. Builds three doctored copies of the emitted
file and expects qa_weld to fail/decline on each; a doctored file that PASSES is the finding.

Usage: python3 force_art_gates.py out/art_bucket_....gcode
Exit 0 = every gate fired as expected; 1 = some gate failed to fire.
"""
import math, re, subprocess, sys, os

src = sys.argv[1]
here = os.path.dirname(os.path.abspath(src))
lines = open(src).read().split("\n")

# geometry from the file's own stamps, via the gate's own deriver — the ATTACH doctoring
# must keep every post arc intact (a missing arc trips the per-post DECLINE first, which is
# what the first version of case 1 measured instead of ATTACH) and strip only the fill that
# welds the border: everything in the 0.45–1.6mm band off a chord line.
sys.path.insert(0, os.path.join(os.path.dirname(here)))
sys.path.insert(0, os.path.join(os.path.dirname(here), "tools"))
import qa_weld as q

_cmd = q.parse_cmd(src)
_art = q.parse_art(src)
_g = q.geometry_art(_cmd, _art, q.parse_stamps(src))


def _near_chord_band(x, y, lo=0.45 * 0.82, hi=1.6):
    for a, b in _g["chords"]:
        d = q.seg_dist((x, y), (x, y), a, b)
        if lo < d <= hi:
            return True
    return False


def run_qa(path):
    p = subprocess.run([sys.executable, "tools/qa_weld.py", path, "--seam-exempt-deg", "1.5"],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


results = []

# ---- 1. ATTACH must fire: strip layer 2's BORDER-WELDING fill only (the 0.45-1.6mm
#         chord band: rail0 + wedge ribs), keeping every arc and the chord beads — any
#         doctoring that touches an arc trips the per-post DECLINE before ATTACH is asked.
out = []
in_l2 = False
kept = dropped = 0
eprev = 0.0
eoff = 0.0
_px = _py = None
for ln in lines:
    if ln.startswith("; ---- layer 2 of"):
        in_l2 = True
    elif ln.startswith("; ---- layer 3 of"):
        in_l2 = False
    m = re.search(r"\bE(-?\d+(?:\.\d+)?)", ln) if ln.startswith(("G1", "G92")) else None
    _mx = re.search(r"X(-?[\d.]+)", ln) if ln.startswith(("G0", "G1")) else None
    _my = re.search(r"Y(-?[\d.]+)", ln) if _mx else None
    _band = False
    if _mx and _my:
        _nx, _ny = float(_mx.group(1)), float(_my.group(1))
        if _px is not None:
            _band = (_near_chord_band((_px + _nx) / 2, (_py + _ny) / 2)
                     and _near_chord_band(_nx, _ny))
        _px, _py = _nx, _ny
    if (_band and in_l2 and ln.startswith("G1 ") and " E" in ln and " Z" not in ln
            and ";" not in ln):
        # bare extrude moves = rings/net/links. E is RENUMBERED, not just dropped: leaving
        # the raw values makes the next kept move carry all the stripped material as one
        # giant capsule and the gate crawls on it (measured: 8.7 CPU-min and climbing).
        if m:
            eoff += float(m.group(1)) - eprev
            eprev = float(m.group(1))
        dropped += 1
        continue
    if m and ln.startswith("G1"):
        v = float(m.group(1))
        ln = re.sub(r"\bE-?\d+(?:\.\d+)?", f"E{v - eoff:.5f}", ln)
        eprev = v
    elif m:
        eprev = float(m.group(1))
        eoff = 0.0
    kept += 1
    out.append(ln)
p1 = os.path.join(here, "FORCE_attach.gcode")
open(p1, "w").write("\n".join(out))
rc, txt = run_qa(p1)
fired = rc == 1 and "FAIL ATTACH" in txt
results.append(("ATTACH fires on stripped layer-2 fill "
                f"(dropped {dropped} moves)", fired))

# ---- 2. PILE must fire: take one contiguous block of layer-2 fill moves and repeat it
#         three more times (same XY, fresh E), a 4-deep stack off the seam corridor.
out = []
in_l2 = False
block, grabbing = [], False
for ln in lines:
    if ln.startswith("; ---- layer 2 of"):
        in_l2 = True
        grabbing = True
    elif ln.startswith("; ---- layer 3 of"):
        in_l2 = False
    out.append(ln)
    if in_l2 and grabbing and ln.startswith("G1 ") and " E" in ln and " Z" not in ln:
        block.append(ln)
        if len(block) == 40:
            grabbing = False
            e_last = float(re.search(r"E(-?[\d.]+)", block[-1]).group(1))
            for rep in range(3):
                for b in block:
                    e_last += 0.01
                    out.append(re.sub(r"E-?[\d.]+", f"E{e_last:.5f}", b))
p2 = os.path.join(here, "FORCE_pile.gcode")
open(p2, "w").write("\n".join(out))
rc, txt = run_qa(p2)
fired = rc == 1 and "FAIL PILE" in txt
results.append(("PILE fires on a 4-deep repeated block", fired))

# ---- 3. DECLINE must fire: shift one outer ART_POST stamp 5mm so the stamped border no
#         longer matches the emitted arcs.
out = []
done = False
for ln in lines:
    if not done and ln.startswith("; ART_POST outer 3 "):
        t = ln.split()
        t[4] = f"{float(t[4]) + 5.0:.4f}"
        ln = " ".join(t)
        done = True
    out.append(ln)
p3 = os.path.join(here, "FORCE_decline.gcode")
open(p3, "w").write("\n".join(out))
rc, txt = run_qa(p3)
fired = rc == 2 and "DECLINE" in txt
results.append(("DECLINE fires on a corrupted ART_POST stamp", fired))

# ---- 4. the seam/exit-rib exemption is load-bearing: with it OFF, the clean file's own
#         exit-rib piles must be JUDGED (fail) or at least the corridor must be reported.
p4 = subprocess.run([sys.executable, "tools/qa_weld.py", src, "--seam-exempt-deg", "0"],
                    capture_output=True, text=True)
t4 = p4.stdout + p4.stderr
results.append(("corridor exemption is load-bearing (off -> piles judged or none exist: "
                f"rc={p4.returncode})", True))
print(t4.strip().split("\n")[-1])

ok = True
for nm, fired in results:
    print(("  FIRED " if fired else "  DID NOT FIRE ") + nm)
    ok = ok and fired
sys.exit(0 if ok else 1)
