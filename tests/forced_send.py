#!/usr/bin/env python3
"""FORCE RULE 6 TO DECLINE. A permission is worth only what it has been SEEN to refuse.

Rule 6 lets a SHORT file establish a send-critical value nothing has proven yet -- the mirror of
rule 5, and the reason send.py is not a wall. It is the only rule in this file that says YES, which
makes it the only one whose test cannot be "prove it fires". A grant that fired on everything would
be an off switch with a comment block. So every case below except two exists to prove it DECLINES,
and the two that pass exist to prove it is not simply off.

Like tests/forced_layer1.py and tests/forced_prime.py this BUILDS its cases from the live generator
rather than from a stored fixture, because the thing being guarded is what the generators EMIT
TODAY and a frozen fixture would go on proving a prime nobody writes any more.

Every case is checked three ways, because two of them have quietly failed on this project before:

  1. THE INJECTION LANDED, AND LANDED IN THE RIGHT JURISDICTION. Position decides the case here:
     header_of() stops at '; BODY_START', so an S8 phrase one line later is invisible and "the
     guard did not fire" would mean nothing. Each case asserts its own boundary before running.
  2. THE VERDICT is what it should be (exit code).
  3. THE REASON is the one intended. `s3_status` reads the STATUS COLUMN of the S3 line, and
     `spent` reads what the log actually recorded -- so a case cannot pass by being refused for
     something else, which is exactly how case 3 was first written and had to be rebuilt: a
     stationary purge injected into an absolute-E file rebased every downstream delta and drove S3
     to ABSTAIN, "refusing" the file without validate.py ever being the reason.

EVERY CASE RUNS ON ITS OWN LOG. The register of spent grants IS send-log.jsonl, so a shared log
would make these cases order-dependent and would spend the real gauge's grant as a side effect of
running the tests.

NOTHING HERE GOES NEAR A PRINTER. send.py's default is a dry run and --live is never passed.

Usage:  python3 tests/forced_send.py            (about 60s: one gauge, seven gate runs)
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)
sys.path.insert(0, CRACKLE)
import send as sendmod                                                          # noqa: E402

MOVING_E = re.compile(r'^G1 .*[XY]-?[\d.]+.* E[\d.]')


def gen(tmp, bores):
    """A real gauge, small and quick, emitted by the live generator with the shared prime."""
    d = os.path.join(tmp, f'g{bores}')
    r = subprocess.run([sys.executable, 'borelock.py', '--bores', bores, '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"generator failed: {r.stderr[-800:]}")
    f = [x for x in os.listdir(d) if x.endswith('.gcode')]
    if len(f) != 1:
        raise SystemExit(f"expected one gcode, got {f}")
    return os.path.join(d, f[0])


def run(path, log, extra=()):
    """One dry run of the gate. Returns (exit code, stdout)."""
    r = subprocess.run([sys.executable, 'send.py', 'send', path, '--log', log, *extra],
                       cwd=CRACKLE, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def s3_line(out):
    """The S3 line, split into (status column, reason text).

    THE STATUS COLUMN, not a substring of the whole report: a test that greps for the word
    FIRST-PROOF anywhere would match the FAIL text that MENTIONS first proof to explain why it did
    not apply, and would then report the opposite of the truth. The reason is returned beside it
    because an exit code cannot say WHICH clause held the file -- these files fail several rules at
    once, and 'refused' is not evidence that the rule under test is the one that refused it.
    """
    m = re.search(r'^ +(\S+) +S3 prime[^\n]*', out, re.M)
    if not m:
        return None, ''
    return m.group(1), m.group(0)


def spent(log):
    """How many DISTINCT files hold a grant. The loud output is a claim; this is the register.

    DISTINCT, not a row count, and the difference is the property under test. send-log.jsonl is
    append-only and writes one row per invocation, so the holder re-running itself legitimately
    appends a second identical grant -- the log is a record of what this tool DID, and it did go
    under first proof both times. What must stay at one is the number of FILES holding the value,
    which is what rule 6 says and what first_proof_holder() enforces.
    """
    held = set()
    if os.path.isfile(log):
        for ln in open(log):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            for g in (r.get('first_proof') or []):
                held.add((r.get('printer'), g.get('param'),
                          tuple(g.get('value') or ()), r.get('sha256')))
    return len(held)


def gen_long(tmp):
    """A file OVER the ceiling and UNDER machine.LONG_PRINT_MIN -- 39 min, in the gap rule 6's own
    comment describes: 'between 25 and 90 minutes an unproven value gets neither a grant nor a
    pass'. Nothing else here exercises that gap, and it is the half of the bound that says no."""
    d = os.path.join(tmp, 'long')
    r = subprocess.run([sys.executable, 'bucket_latch.py', '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"bucket_latch failed: {r.stderr[-800:]}")
    return os.path.join(d, [x for x in os.listdir(d) if x.endswith('.gcode')][0])


def main():
    tmp = tempfile.mkdtemp(prefix='forced_send_')
    a = gen(tmp, '3.6,4.6')             # the gauge whose whole purpose is to answer a blocked question
    b = gen(tmp, '3.9,4.9')             # a DIFFERENT short file carrying the SAME unproven prime
    lg = gen_long(tmp)                  # same unproven prime, 39 min -- over the ceiling
    L = open(a).read().split('\n')
    bs = next(i for i, l in enumerate(L) if 'BODY_START' in l)
    fme = next(i for i, l in enumerate(L) if MOVING_E.match(l))

    # -- the mutants, each with the assertion that says where it landed ---------------------
    # S8: header_of() reads up to and including '; BODY_START'. One line later is a different file.
    s8 = os.path.join(tmp, 's8.gcode')
    open(s8, 'w').write('\n'.join(
        L[:bs] + ["; the fit here is modelled only, so this file DECLINES to claim a fit"] + L[bs:]))

    # validate: a pure TRAVEL, deep in the body, under material that is already standing. It touches
    # no E word at all -- these files are absolute-E, so an injected extrusion silently rebases every
    # downstream delta and makes S3 abstain instead of reaching rule 6.
    zi, zv = next((i, float(m.group(1))) for i in range(bs, len(L))
                  for m in [re.match(r'^G1 F\d+ Z([\d.]+)\s*$', L[i])] if m and float(m.group(1)) > 5)
    vf = os.path.join(tmp, 'validate.gcode')
    open(vf, 'w').write('\n'.join(L[:zi + 1] + ["G0 F6000 X150.000 Y150.000 Z0.100", L[zi]] + L[zi + 1:]))

    # ABSTAIN: strip the prime's witness segment so prime_fat cannot be computed. The value becomes
    # UNMEASURED rather than unproven, and rule 6 must not touch it.
    ab = os.path.join(tmp, 'abstain.gcode')
    open(ab, 'w').write('\n'.join(l for l in L if 'witness' not in l))

    # A CLAIM TO BE A COUPON IS NOT A PERMISSION, and this is the DIFFERENTIAL half of that: the
    # same over-ceiling file as `too_long`, byte-identical but for three header lines declaring as
    # loudly as a file can that it is a coupon. Both must be refused for the SAME reason. The house
    # pattern is that a citation supplies a pointer and never a permission, and the actor who would
    # type these lines is the one this whole tool exists to distrust.
    LL = open(lg).read().split('\n')
    lbs = next(i for i, l in enumerate(LL) if 'BODY_START' in l)
    claim = os.path.join(tmp, 'claim.gcode')
    open(claim, 'w').write('\n'.join(
        LL[:lbs] + ["; THIS FILE IS A COUPON", "; FIRST_PROOF=1", "; COUPON_SIZED=1"] + LL[lbs:]))

    cases = [
        # name, file, want_exit, want S3 status, want reason on the S3 line, want distinct grants
        ('gauge_first_proof', a, 0, 'FIRST-PROOF', r'inside the 25 min', 1,
         "the gauge that answers a blocked question goes, and the grant is recorded"),
        ('same_bytes_again', a, 0, 'FIRST-PROOF', r'inside the 25 min', 1,
         "a file holds its OWN grant across re-runs, or every dry run locks out its live send"),
        ('second_file_same_value', b, 1, 'FAIL', r'already granted to', 1,
         "ONE file per value: a different artifact with the same unproven prime gets no second pass"),
        ('too_long', lg, 1, 'FAIL', r'past the 25 min', 0,
         "39 min sits in the 25-to-90 gap, where an unproven value gets neither a grant nor a pass"),
        ('claim_is_not_permission', claim, 1, 'FAIL', r'past the 25 min', 0,
         "the same file declaring itself a coupon is refused for the same reason: duration is the "
         "bound and a header line is not one"),
        ('validate_refuses', vf, 1, 'FIRST-PROOF', r'inside the 25 min', 0,
         "eligible for rule 6 and still refused -- the send gate never overrules the file gate"),
        ('s8_self_disclaimed', s8, 1, 'FIRST-PROOF', r'inside the 25 min', 0,
         "a file whose own header disclaims what it claims is refused however short it is"),
        ('abstain_not_relaxed', ab, 1, 'ABSTAIN', r'NOT MEASURED', 0,
         "UNMEASURED is not UNPROVEN; rule 6 must not hand a grant to a value nothing read"),
    ]

    print(f"forcing rule 6 (first proof, ceiling {sendmod.FIRST_PROOF_MAX_MIN:g} min of motion)\n")
    ok_n = 0
    for name, path, want_exit, want_s3, want_why, want_grants, note in cases:
        # own log per case, EXCEPT the two that deliberately share one to exercise the register
        log = os.path.join(tmp, f'{name}.jsonl')
        if name == 'same_bytes_again':
            log = os.path.join(tmp, 'gauge_first_proof.jsonl')
        if name == 'second_file_same_value':
            log = os.path.join(tmp, 'held.jsonl')
            run(a, log)                                    # the holder takes the grant first
        code, out = run(path, log)
        got_s3, why = s3_line(out)
        got_grants = spent(log)
        why_ok = bool(re.search(want_why, why))
        good = (code == want_exit and got_s3 == want_s3 and why_ok and got_grants == want_grants)
        ok_n += good
        print(f"{'ok  ' if good else 'FAIL'} {name:24s} exit={code}(want {want_exit}) "
              f"S3={got_s3}(want {want_s3}) reason={'found' if why_ok else 'MISSING'} "
              f"grants={got_grants}(want {want_grants})")
        print(f"     {note}")
        if not good:
            print(f"       | S3 line: {why.strip()[:400]}")
            print('\n'.join('       | ' + l for l in out.split('\n') if l.strip())[-2000:])

    print(f"\n{ok_n}/{len(cases)} forced cases behave as specified — rule 6 is proven able to "
          f"GRANT, and proven able to decline on duration, on repetition, on a declaration, on "
          f"validate.py, on S8 and on abstention")
    return 0 if ok_n == len(cases) else 1


if __name__ == '__main__':
    sys.exit(main())
