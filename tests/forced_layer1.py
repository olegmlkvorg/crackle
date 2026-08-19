#!/usr/bin/env python3
"""FORCE R9 TO FIRE. A guard is worth only what it has been SEEN to reject.

The other fixtures in tests/forced/ are static gcode. This one BUILDS its cases from the live
generator instead, for a reason R9 exists to address: a stored fixture freezes the first layer as
it was on the day it was saved, and the failure this gate is about is the first layer CHANGING.
A harness that regenerates proves the gate and the generator still agree today.

Every case is checked three ways, because two of them have quietly failed on this project before:

  1. THE INJECTION LANDED. A mutant that fails to apply reads exactly like a passing guard.
  2. THE VERDICT is what it should be (exit code).
  3. THE REASON is the one intended. A file that fails for an unrelated reason is not evidence
     that R9 fired -- "the guard passed the failure" is a lesson already paid for here.

Usage:  python3 tests/forced_layer1.py            (about 90s: three buckets, ten validations)
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)
COUPON = 'zladder_k2plus_pla_6cell_w2_p1.6.gcode'
REQUIRED_ARTIFACTS = ('zladder_k2plus_pla_6cell_w2_p1.6.gcode',)
OFF = re.compile(r'^SET_GCODE_OFFSET .*$', re.M)


def gen(tmp, name, h1, w1):
    """A real bucket at a named first-layer operating point. Small, so ten of these are cheap."""
    d = os.path.join(tmp, name)
    r = subprocess.run([sys.executable, 'bucket_towers.py', '--dia', '60', '--height', '10',
                        '--h1', str(h1), '--w1', str(w1), '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"generator failed for {name}: {r.stderr[-800:]}")
    f = [x for x in os.listdir(d) if x.endswith('.gcode')]
    if len(f) != 1:
        raise SystemExit(f"expected one gcode for {name}, got {f}")
    return os.path.join(d, f[0])


def stamp(txt, line):
    return re.sub(r'(^; LAYER1_WIDTH=.*$)', lambda m: m.group(1) + '\n' + line, txt,
                  count=1, flags=re.M)


def main():
    tmp = tempfile.mkdtemp(prefix='forced_layer1_')
    artifacts = os.environ.get('CRACKLE_ARTIFACTS', os.path.join(CRACKLE, 'out'))
    coupon_source = os.path.join(artifacts, COUPON)
    if not os.path.isfile(coupon_source):
        raise SystemExit(f"NOT RUN: required artifact is absent: {coupon_source}")
    # validate.py resolves a citation beside the candidate first. Copy the measured coupon into
    # this test's temporary directory; never write into or regenerate the historical corpus.
    shutil.copy2(coupon_source, os.path.join(tmp, COUPON))
    proven = open(gen(tmp, 'proven', 0.10, 2.00)).read()     # the pair that printed and held
    starved = open(gen(tmp, 'starved', 0.15, 1.33)).read()   # the bamboo base that lifted
    wide15 = open(gen(tmp, 'wide15', 0.15, 2.00)).read()     # unproven, but a ladder cell tested it

    cases = [
        # name, text, expect_ok, a phrase that must appear, why this case exists
        ('proven', proven, True, 'proven weld',
         'the proven pair must not be condemned'),
        ('no_offset', OFF.sub('', proven, count=1), False, 'R9 no SET_GCODE_OFFSET',
         'THE hole: validate.py had zero occurrences of SET_GCODE_OFFSET'),
        ('offset_contradicts', OFF.sub('SET_GCODE_OFFSET Z=-0.050', proven, count=1), False,
         'contradicts the file', 'offset disagrees with the gap its own header declares'),
        ('unproven_uncited', starved, False, 'It cites no coupon',
         'the real 2026-08-06 bamboo parameters, which printed as lifted strands'),
        ('coupon_missing_file', stamp(wide15, '; COUPON=nosuchladder.gcode h1=0.150 w1=2.00 '
                                              'verdict=welded read=2026-08-06'),
         False, 'no such file exists', 'a citation nobody can open is not evidence'),
        ('coupon_wrong_width', stamp(starved, f'; COUPON={COUPON} h1=0.150 w1=1.33 '
                                              f'verdict=welded read=2026-08-06'),
         False, 'not the 1.33mm cited', 'the ladder printed 0.15 at 2.00 wide, never at 1.33'),
        ('coupon_not_read', stamp(wide15, f'; COUPON={COUPON} h1=0.150 w1=2.00 '
                                          f'verdict=printed read=2026-08-06'),
         False, 'Only \'welded\' is evidence', 'printed is not read, and read is not welded'),
        ('coupon_drifted', stamp(wide15, f'; COUPON={COUPON} h1=0.100 w1=2.00 '
                                         f'verdict=welded read=2026-08-06'),
         False, 'drifted from the part', 'citation names numbers this file does not land'),
        ('fake_ladder', stamp(starved, '; Z_LADDER=1'), False, 'that is a part, not a ladder',
         'the ladder exemption must not survive being counted on a part'),
        # THE ESCAPE HATCH MUST ACTUALLY OPEN. A gate nothing can legitimately pass is a gate that
        # gets switched off, and RULES.md says false positives are how that happens.
        ('coupon_good', stamp(wide15, f'; COUPON={COUPON} h1=0.150 w1=2.00 '
                                      f'verdict=welded read=2026-08-06'),
         True, 'EXCUSED', 'a cited ladder cell that printed exactly these numbers'),
    ]

    bad = 0
    for name, txt, want_ok, phrase, why in cases:
        p = os.path.join(tmp, name + '.gcode')
        open(p, 'w').write(txt)
        # (1) the injection landed
        landed = (txt != proven) or name == 'proven'
        if name == 'unproven_uncited':
            landed = 'SET_GCODE_OFFSET Z=-0.100' in txt
        r = subprocess.run([sys.executable, 'validate.py', p], cwd=CRACKLE,
                           capture_output=True, text=True)
        got_ok = r.returncode == 0
        out = r.stdout + r.stderr
        # (2) the verdict and (3) the reason
        ok = landed and got_ok == want_ok and phrase in out
        bad += not ok
        print(f"{'ok  ' if ok else 'BAD '} {name:20s} injected={landed} "
              f"verdict={'pass' if got_ok else 'fail'} (want {'pass' if want_ok else 'fail'}) "
              f"reason={'found' if phrase in out else 'MISSING: ' + phrase!r}")
        if not ok:
            for l in out.splitlines():
                if 'R9' in l or 'FAIL' in l:
                    print(f"        {l.strip()}")
    print(f"\n{len(cases) - bad}/{len(cases)} forced cases behave as specified — "
          f"{'R9 is proven able to fire and able to be satisfied' if not bad else 'SOMETHING IS WRONG'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
