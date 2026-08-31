#!/usr/bin/env python3
"""FORCE THE RETRACT AND L1_BENCH SEAMS TO FIRE. A guard is worth only what it has been SEEN to
reject — and both of these seams' first red-proofs were hand-run on 2026-08-31 through the repo's
own documented zsh trap (an unsplit $VAR ran nothing and grep counted zero), which is exactly why
the proof belongs in the suite and not in a shell history.

RETRACT (Oleg: "we need to retract befor movement, as we crerating a lot of nets during move"):
a declared '; RETRACT=<mm>' admits E-only pullbacks no deeper than declared. Three directions:
the clean file passes with its retracts COUNTED; stripping the stamp turns every retract into the
old unintended-retraction refusal; one retract deepened past the declaration is refused alone.

L1_BENCH (Oleg: "we need to benchmark first layer extrusion level"): the Z ladder's mirror —
3+ metered rates counted at the file's lowest landed height. A uniform-rate part wearing the
stamp is refused as counted, not believed.
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)


def gen(tmp):
    d = os.path.join(tmp, 'bench')
    r = subprocess.run([sys.executable, 'hangertag.py',
                        '--heights', '0.44', '--fills', '1.05,0.90,0.75', '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"generator failed: {r.stderr[-800:]}")
    f = [x for x in os.listdir(d) if x.endswith('.gcode')]
    if len(f) != 1:
        raise SystemExit(f"expected one gcode, got {f}")
    return os.path.join(d, f[0])


def validate(path):
    r = subprocess.run([sys.executable, 'validate.py', path],
                       cwd=CRACKLE, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix='forced_rb_')
    clean = gen(tmp)
    txt = open(clean).read()
    if '; RETRACT=' not in txt or '; L1_BENCH=1' not in txt:
        raise SystemExit("FAIL: the generator no longer emits the RETRACT/L1_BENCH stamps — this "
                         "test's subjects are gone; re-point it before trusting the seams.")

    rc, out = validate(clean)
    if rc != 0:
        raise SystemExit(f"FAIL: the CLEAN benchmark file is refused — a seam that rejects its "
                         f"own shape is a wall.\n{out[-1500:]}")
    if 'declared retract(s)' not in out:
        raise SystemExit("FAIL: the clean file passes but its retracts were never COUNTED — an "
                         "exemption that is not counted is invisible.")
    if 'L1_BENCH=1\' is declared AND counted' not in out:
        raise SystemExit("FAIL: the clean file passes but the benchmark count never ran.")

    p = os.path.join(tmp, 'undeclared.gcode')
    open(p, 'w').write(re.sub(r'^; RETRACT=[\d.]+\n', '', txt, count=1, flags=re.M))
    rc, out = validate(p)
    if rc == 0 or 'unintended retraction' not in out:
        raise SystemExit(f"FAIL: with the stamp stripped, every retract must fail as the old "
                         f"unintended retraction.\n{out[-1200:]}")

    m = re.search(r'^G1 E(-?[\d.]+) F2400   ; RETRACT.*$', txt, re.M)
    if not m:
        raise SystemExit("FAIL: no retract move found to deepen — injection cannot land.")
    deep = txt.replace(m.group(0),
                       f"G1 E{float(m.group(1)) - 1.0:.5f} F2400   ; RETRACT deeper", 1)
    p = os.path.join(tmp, 'toodeep.gcode')
    open(p, 'w').write(deep)
    rc, out = validate(p)
    if rc == 0 or 'unintended retraction' not in out:
        raise SystemExit(f"FAIL: a retract 1mm past the declaration must be refused.\n{out[-1200:]}")

    # a PART wearing the benchmark stamp: heights ladder file (uniform rate per its own cells is
    # not the point — take the clean file and flatten every floor rate by regenerating with one
    # fill... a single-fill run is refused by the generator itself, so doctor the STAMP onto a
    # uniform-rate artifact instead: the ladder-mode file.
    d2 = os.path.join(tmp, 'lad')
    r = subprocess.run([sys.executable, 'hangertag.py', '--heights', '0.16,0.22,0.28',
                        '--out', d2], cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ladder generator failed: {r.stderr[-800:]}")
    lf = os.path.join(d2, [x for x in os.listdir(d2) if x.endswith('.gcode')][0])
    fake = open(lf).read().replace('; Z_LADDER=1', '; L1_BENCH=1', 1)
    p = os.path.join(tmp, 'fakebench.gcode')
    open(p, 'w').write(fake)
    rc, out = validate(p)
    if rc == 0 or 'does not survive being counted' not in out:
        raise SystemExit(f"FAIL: a height-ladder wearing the benchmark stamp must be refused for "
                         f"the counted reason (its floor has ONE rate).\n{out[-1200:]}")

    print("PASS: clean benchmark accepted with retracts and rates counted; stripped stamp, "
          "too-deep retract, and a part wearing the benchmark stamp all refused, each for its "
          "stated reason.")


if __name__ == '__main__':
    main()
