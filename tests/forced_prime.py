#!/usr/bin/env python3
"""FORCE R10 TO FIRE. A guard is worth only what it has been SEEN to reject.

R10 refuses extrusion with the head standing still, before anything is pinned to the plate --
Oleg's 2026-08-06 photograph of a clump of filament on the nozzle and then of that clump dropped
into a printing plate. Like tests/forced_layer1.py this BUILDS its cases from the live generator
rather than from a stored fixture, because the thing being guarded is the OPENING SEQUENCE and a
frozen fixture would go on proving a prime nobody emits any more.

Every case is checked three ways, because two of them have quietly failed on this project before:

  1. THE INJECTION LANDED, and landed in R10's JURISDICTION. Position matters here in a way it did
     not for R9: the same three lines injected AFTER the first moving extrusion are a different
     case with a different correct answer, so "the mutant did not fire" would be meaningless
     without checking which side of that boundary it landed on.
  2. THE VERDICT is what it should be (exit code).
  3. THE REASON is the one intended. A file that fails for an unrelated reason is not evidence
     that R10 fired.

THE LAST TWO CASES ARE THE ONES THAT MATTER MOST, and they are the ones a naive harness omits:
a rule that fires on everything is not a measurement. `pinned_dwell` proves R10 DECLINES a
stationary extrusion once material is down (the strand has a far end, so the mechanism does not
apply), and `as_generated` proves the prime this project now emits satisfies its own gate.

Usage:  python3 tests/forced_prime.py            (about 30s: one gauge, five validations)
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)

# The purge shape borelock.py, zladder.py and stencil_coupon.py all carried until 2026-08-06:
# lift clear of the plate, dump 20mm of filament (48.1 mm3) into open air, then drive the nozzle
# 1.9mm DOWN into the pile. This is the photograph.
AIR_PURGE = ["G1 F600 Z2.000",
             "G1 E20 F300                      ; PRIME purge, LIFTED to Z2",
             "G1 F600 Z0.100"]
# The shape bucket_towers.py and bucket_latch.py carried: same dump, at the press gap, which this
# repo had already recorded (presstest.py:168) as the WORSE of the two.
GAP_PURGE = ["G1 E12 F300                          ; PRIME stationary purge"]

MOVING_E = re.compile(r'^G1 .*[XY]-?[\d.]+.* E[\d.]')


def gen(tmp):
    """A real gauge, small and quick, emitted by the live generator with the shared prime."""
    d = os.path.join(tmp, 'src')
    r = subprocess.run([sys.executable, 'borelock.py', '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"generator failed: {r.stderr[-800:]}")
    f = [x for x in os.listdir(d) if x.endswith('.gcode')]
    if len(f) != 1:
        raise SystemExit(f"expected one gcode, got {f}")
    return open(os.path.join(d, f[0])).read().split('\n')


def inject(lines, after, block):
    i = next(n for n, l in enumerate(lines) if after in l)
    return lines[:i + 1] + block + lines[i + 1:]


def first_moving_e(lines):
    return next(n for n, l in enumerate(lines) if MOVING_E.match(l))


def main():
    tmp = tempfile.mkdtemp(prefix='forced_prime_')
    base = gen(tmp)

    air = inject(base, 'PRIME descend', AIR_PURGE)
    gap = inject(base, 'PRIME descend', GAP_PURGE)
    pinned = inject(base, '; ---- plate layer 1', [])
    # AFTER the first bead is down, which is the boundary R10 is written around.
    j = first_moving_e(pinned)
    pinned = pinned[:j + 1] + ["G1 E999 F300                     ; injected mid-print dwell"] \
        + pinned[j + 1:]
    # No position has ever been commanded, so a parser that needs a previous point to decide
    # "did it move" has none. That case must read as STATIONARY, not as unknown.
    nopos = [l for l in base if not (l.startswith('G0 ') and ' X' in l)]
    nopos = inject(nopos, 'PRIME descend', ["G1 E20 F300                      ; nowhere to move from"])

    cases = [
        # name, lines, expect_ok, phrase that must appear, why this case exists
        ('as_generated', base, True, 'passes',
         'the prime this project emits must satisfy its own gate'),
        ('air_purge', air, False, 'STANDING STILL at Z2.000',
         "the lifted free-air dump in Oleg's photograph"),
        ('gap_purge', gap, False, 'STANDING STILL at Z0.100',
         'the press-gap dump, which presstest.py recorded as the worse one'),
        ('no_position', nopos, False, 'STANDING STILL',
         'extruding before any XY was ever commanded reads as stationary, not as unknown'),
        # THE RULE MUST ALSO DECLINE. A gate that refuses every stationary E would be refusing the
        # ~20 solid.py files that step Z while extruding at a spiral seam, which is a different
        # question -- there the previous bead holds the far end of the strand.
        ('pinned_dwell', pinned, None, 'not refused',
         'once material is down the mechanism does not apply; R10 must count it, not refuse it'),
    ]

    bad = 0
    for name, lines, want_ok, phrase, why in cases:
        txt = '\n'.join(lines)
        p = os.path.join(tmp, name + '.gcode')
        open(p, 'w').write(txt)
        # (1) the injection landed, AND landed on the right side of the pinning boundary
        if name == 'as_generated':
            landed = True
        else:
            hits = [n for n, l in enumerate(lines, 1) if re.match(r'G1 E\d+ F300', l)]
            fme = first_moving_e(lines) + 1
            want_before = name != 'pinned_dwell'
            landed = len(hits) == 1 and ((hits[0] < fme) == want_before)
        r = subprocess.run([sys.executable, 'validate.py', p], cwd=CRACKLE,
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        got_ok = r.returncode == 0
        # (2) the verdict -- None means "R10 must not be the one complaining", whatever else does
        if want_ok is None:
            verdict = not any('R10' in l and 'FAIL' in l for l in out.splitlines())
        else:
            verdict = got_ok == want_ok
        # (3) the reason
        ok = landed and verdict and phrase in out
        bad += not ok
        print(f"{'ok  ' if ok else 'BAD '} {name:14s} injected={landed} "
              f"verdict={'pass' if got_ok else 'fail'} "
              f"reason={'found' if phrase in out else 'MISSING: ' + repr(phrase)}   {why}")
        if not ok:
            for l in out.splitlines():
                if 'R10' in l or 'FAIL' in l:
                    print(f"        {l.strip()}")
    print(f"\n{len(cases) - bad}/{len(cases)} forced cases behave as specified — "
          f"{'R10 is proven able to fire, and proven able to decline' if not bad else 'SOMETHING IS WRONG'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
