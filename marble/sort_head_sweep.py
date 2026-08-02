#!/usr/bin/env python3
"""SORT HEAD FUNCTION GATE -- the only test that decides this part.

A head that passes qa_stl and its own self-verify still sorted 1 pour in 9 (v1). Mesh validity is
not function here. FUNCTION is "a marble poured anywhere in the bowl ends up on the right side of
the chute's crest", and that can only be answered with the head MERGED ONTO THE REAL CHUTE and
marbles poured in. So this runs the two existing sim harnesses against the emitted meshes:
  sim/chain_test.mjs        the shared chain harness: O12 and O16 poured 0/20/35mm off centre.
                            For a head whose sieve bore is under O12 this is the HOLD test -- both
                            sizes must stay in the bowl.
  sim/sort_head_probe.mjs   the drop marble, nine pours 0..40mm off centre. Three pours cannot
                            tell a design change from noise: measured 2026-08-03, three geometries
                            that differ by nothing physical came out 1/3, 2/3 and 1/3.

IT RUNS THE KNOWN-BAD EVERY TIME. A gate that has only ever passed is decoration, so this builds
the v1 head (--no-extension) alongside the real one and requires it to FAIL. If the known-bad
starts passing, the gate is broken and this says so instead of reporting a green run.

Usage: python3 sort_head_sweep.py sort_chute_16_14.stl [--hold 16] [--drop 10]

HOW THE CREST LAW IN sort_head_stl WAS MEASURED, so it can be re-derived rather than believed.
Vary ONLY the chute's rail crest, everything else identical, and run the nine pours:
    for r in 15.25 17.5 19.0; do
      python3 spiral_chute_stl.py --hold 22 --drop 12 --rail $r --pitch 20 --turns 3 \\
              --out c$r.stl
      python3 sort_head_stl.py --chute c$r.stl --hold 22 --drop 12 --out h$r.stl
      node ../sim/sort_head_probe.mjs c$r.stl h${r}_seat0.stl 1 1 12
    done
    crest O15.25  tube stops 1.7mm above the crest   4/9
    crest O17.50  tube reaches the crest             7/9
    crest O19.00  tube lines the whole shaft         9/9
And vary ONLY the drop marble against the one real chute:
    for d in 12 11 10 9 8; do python3 sort_head_stl.py --chute sort_chute_16_14.stl --drop $d; done
    O12 2/9   O11 5/9   O10 9/9   O9 9/9   O8 9/9      (predicted cutoff: O10.30)
"""
import argparse, os, re, subprocess, sys

import sort_head_stl as sh

SIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim")


def node(script, *args):
    r = subprocess.run(["node", script] + [str(x) for x in args],
                       cwd=SIM, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{script} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def build(chute, hold, drop, extension, tag):
    b = sh.build_profile(hold, drop, 100.0, chute, extension, None)
    out = f"sort_head_gate_{tag}.stl"
    sh.emit(out, b["prof"], 144)
    seat = out.replace(".stl", "_seat0.stl")
    sh.shift_z(out, seat, -b["seat_local"])
    return b, os.path.abspath(seat)


def measure(chute, seat, drop):
    """Sort rate over nine pours + the hold behaviour, both off the emitted meshes."""
    p = node("sort_head_probe.mjs", os.path.abspath(chute), seat, 1, 1, drop)
    m = re.search(r"SHAFT (\d+)/(\d+)", p)
    marks = "".join("S" if "SHAFT" in l else "." for l in p.splitlines()
                    if l.strip().startswith("final"))
    c = node("chain_test.mjs", os.path.abspath(chute), seat)
    held = sum(1 for l in c.splitlines() if "O16" in l and "held" in l)
    leaked = [l.strip() for l in c.splitlines()
              if ("O12" in l or "O16" in l) and "held" not in l]
    return int(m.group(1)), int(m.group(2)), marks, held, leaked


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chute")
    ap.add_argument("--hold", type=float, default=16.0)
    ap.add_argument("--drop", type=float, default=10.0)
    a = ap.parse_args()

    zs, rs = sh.ring_profile(a.chute)
    top, bot, cr = sh.crest_zone(zs, rs)
    print(f"chute {a.chute}: crest O{2*cr:.2f}, the run that can catch a marble is z {bot:.0f}"
          f"..{top:.0f} ({top-bot:.0f}mm). Largest marble a guide tube can carry down it: "
          f"O{sh.max_guided_drop(2*cr):.2f}")

    rows = []
    for tag, ext in (("v1", False), ("guided", True)):
        b, seat = build(a.chute, a.hold, a.drop, ext, tag)
        s, n, marks, held, leaked = measure(a.chute, seat, a.drop)
        unlined = max(0.0, b["fit"]["unlined"]) if ext else (b["fit"]["z_fl"] - b["fit"]["crest_bot"])
        rows.append((tag, ext, b, s, n, marks, held, leaked, unlined))
        print(f"\n{tag}: lower tube {b['ext_l']:.1f}mm, {unlined:.1f}mm of crest unlined")
        print(f"   O{a.drop:g} poured 0,5,10,...,40mm off centre -> down the shaft {s}/{n}  [{marks}]")
        print(f"   O{a.hold:g} poured 0,20,35mm off centre       -> held in the bowl {held}/3")
        for l in leaked:
            print(f"   LEAK {l}")

    good = next(r for r in rows if r[1])
    bad = next(r for r in rows if not r[1])
    checks = [
        ("sorts every pour", good[3] == good[4],
         f"{good[3]}/{good[4]} of the O{a.drop:g} pours went down the shaft"),
        ("holds the big one", good[6] == 3, f"{good[6]}/3 O{a.hold:g} pours stayed in the bowl"),
        ("nothing oversized leaks", not good[7],
         f"{len(good[7])} pour(s) of a marble the sieve should block got past it"),
        ("crest fully lined", good[8] <= 1e-6, f"{good[8]:.2f}mm of crest left unlined"),
        ("GATE FIRES on the known-bad", bad[3] < bad[4],
         f"v1 (no lower tube, {bad[8]:.0f}mm of crest unlined) sorted {bad[3]}/{bad[4]}; if this "
         f"ever reads {bad[4]}/{bad[4]} the gate has stopped measuring anything"),
    ]
    ok = True
    for name, g, msg in checks:
        print("  %s %-30s %s" % ("PASS" if g else "FAIL", name, msg))
        ok = ok and g
    if not ok:
        raise SystemExit("\nFUNCTION GATE: FAIL")
    print("\nFUNCTION GATE: PASS. Sim only: sim_core.mjs's friction 0.5 / restitution 0.15 are "
          "ASSUMED, and nothing here has been printed.")


if __name__ == "__main__":
    main()
