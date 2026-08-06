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

THE LEDGER THE LIVE GCODE IS JUDGED AGAINST IS A COPY THIS FILE CONTROLS -- see hermetic_ledger()
for the two opposite staleness directions that forces, one of which took this suite from 8/8 to 1/8
on 2026-08-06. The gcode is still the live generator's, byte for byte, with the real prime in it.

Every case is checked three ways, because two of them have quietly failed on this project before:

  1. THE INJECTION LANDED, AND LANDED IN THE RIGHT JURISDICTION. Position decides the case here:
     header_of() stops at '; BODY_START', so an S8 phrase one line later is invisible and "the
     guard did not fire" would mean nothing. Each case asserts its own boundary before running.
     The hermetic ledger is checked the same way and off the EMITTED copy, not off the model of it
     this file used to write the copy: the subprocess re-imports it and reports the rows that
     survived.
  2. THE VERDICT is what it should be (exit code).
  3. THE REASON is the one intended. `s3_status` reads the STATUS COLUMN of the S3 line, and
     `spent` reads what the log actually recorded -- so a case cannot pass by being refused for
     something else, which is exactly how case 3 was first written and had to be rebuilt: a
     stationary purge injected into an absolute-E file rebased every downstream delta and drove S3
     to ABSTAIN, "refusing" the file without validate.py ever being the reason.

EVERY CASE RUNS ON ITS OWN LOG. The register of spent grants IS send-log.jsonl, so a shared log
would make these cases order-dependent and would spend the real gauge's grant as a side effect of
running the tests.

NOTHING HERE GOES NEAR A PRINTER. `--live` is passed by exactly one case, `live_no_host`, whose
whole subject is that --live WITHOUT a host is refused; no --printer-host string exists anywhere in
this file, and send.py's upload is unreachable without one (`if ok and args.live:`, below a clause
that has already set ok False). Every other case is a dry run, which is send.py's default.

Usage:  python3 tests/forced_send.py    (three generated files, nine cases, ten gate runs — the
                                         tenth is the holder pre-run in second_file_same_value)
"""
import collections, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)
sys.path.insert(0, CRACKLE)
import send as sendmod                                                          # noqa: E402

MOVING_E = re.compile(r'^G1 .*[XY]-?[\d.]+.* E[\d.]')

# The gate is three files and they resolve each other by __file__, not by cwd: send.py and
# validate.py both `sys.path.insert(0, dirname(abspath(__file__)))` before `import machine`, and
# machine.py imports nothing but math. So a copy of these three in one directory is a complete,
# self-consistent gate, and the copy's machine.py is the one both copies import. Nothing else in
# the repo is imported at run time; coupon files are still resolved against the real repo because
# run() keeps cwd=CRACKLE.
GATE_FILES = ('send.py', 'validate.py', 'machine.py')


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


def measured_prime(path):
    """The prime triple THIS file actually carries, read by the gate's own measuring code.

    Read, never assumed: the same generator emits (5, 1.2, 0) on one file and (5, 1.20002, 0) on
    another, and which ledger row that matches is decided by send.py's tolerances and not by a
    literal typed here. Using the gate's own scan() and part_values() means the test can never
    disagree with the gate about what value is under test.
    """
    meas = sendmod.scan(path)
    zerr = sendmod.machine.ZERR.get(meas['printer'])
    return meas['printer'], sendmod.part_values(path, meas, zerr)['prime']


def hermetic_ledger(tmp, files):
    """Copy the whole gate into `tmp` and, IN THE COPY ONLY, make the prime `files` carry UNPROVEN.

    Returns the path of the copied send.py. machine.py in the real repo is never touched.

    WHY A COPY AT ALL, and it is the reason this suite exists. Rule 6 only reaches a value NOTHING
    HAS PROVEN, so every case below needs one to test against. There are exactly two ways to supply
    one and BOTH go stale, in OPPOSITE directions:

      STALE FIXTURE -- freeze a synthetic gcode carrying a made-up prime. The day a generator
                       changes its purge, this suite goes on proving a prime nobody writes any
                       more: rule 6 verified against a file no machine will ever see. The module
                       docstring above rejects this, correctly, and that reasoning stands.
      STALE LEDGER  -- take the prime off the live generator, as this suite did, and the day that
                       value is legitimately ACCEPTED into machine.PROVEN_SEND it stops being
                       unproven. S3 reports PASS, no grant is issued, and every case that asserts
                       on a grant fails. That is not hypothetical: (5.0, 1.2, 0.0) was admitted on
                       2026-08-06 after the bore gauge printed it and Oleg read the plate, and this
                       suite went from 8/8 to 1/8 without a line of gate code changing.

    Splitting them closes both. The GCODE stays live -- generated here, this run, with whatever
    prime the generators write today -- so the fixture direction cannot fire. The LEDGER is this
    copy, with every row matching that live prime removed, so the acceptance direction cannot fire
    either: an acceptance is stripped, and a retraction leaves nothing to strip. Neither edit to
    machine.PROVEN_SEND can move this suite again, in either direction, and that is permanent
    rather than something a future session has to notice.

    WHAT IS NOT RELAXED. Only `prime` rows are dropped, and only those matching a value one of
    these live files actually carries, matched with send.py's own tolerances. Every other parameter
    is judged against the real ledger, so S3 stays the deciding line and a case cannot pass by
    having some unrelated rule quietly weakened underneath it.
    """
    d = os.path.join(tmp, 'hermetic-gate')
    os.makedirs(d, exist_ok=True)
    for f in GATE_FILES:
        shutil.copy2(os.path.join(CRACKLE, f), os.path.join(d, f))

    printers, primes = set(), []
    for p in files:
        pr, val = measured_prime(p)
        printers.add(pr)
        primes.append(val)
    if len(printers) != 1 or None in printers:
        raise SystemExit(f"hermetic ledger: expected one named printer across the case files, "
                         f"got {printers}")
    printer = printers.pop()

    rows = sendmod.machine.PROVEN_SEND[printer]['prime']
    drop = sorted(i for i, r in enumerate(rows)
                  if any(sendmod._vec_close(tuple(r[:-1]), v, sendmod.TOLS['prime'])
                         for v in primes))

    # Dropped BY INDEX against a length assert, not by re-typing float literals a rounding could
    # miss: the indices are computed just above from the very rows this copy was made from, and the
    # assert is what makes that stay true if anyone ever copies this patch somewhere else.
    with open(os.path.join(d, 'machine.py'), 'a') as fh:
        fh.write(f'''

# ---------------------------------------------------------------------------------------------
# APPENDED BY tests/forced_send.py -- THIS IS A TEST COPY, NOT THE REPO'S machine.py.
# The rows below carry the prime the live generator writes today. They are removed HERE ONLY so
# rule 6 has an unproven value to reach, which is the only thing that can prove it DECLINES. See
# hermetic_ledger() for why neither a frozen fixture nor the live ledger can do this job.
_rows = PROVEN_SEND[{printer!r}]['prime']
if len(_rows) != {len(rows)}:
    raise SystemExit("hermetic ledger: PROVEN_SEND[{printer!r}]['prime'] is not the list this "
                     "patch was computed against")
PROVEN_SEND[{printer!r}]['prime'] = [r for i, r in enumerate(_rows) if i not in {set(drop) or set()!r}]
SEND_LEDGER_VERSION = SEND_LEDGER_VERSION + "+forced_send-hermetic"
''')

    # THE INJECTION LANDED -- asserted off the EMITTED copy by importing it, never off the plan
    # that wrote it. A patch that silently landed in a dict nobody reads would leave every case
    # below testing the live ledger again and reporting green about it.
    chk = subprocess.run(
        [sys.executable, '-c',
         'import json,sys,machine;'
         'print(json.dumps([list(r[:-1]) for r in machine.PROVEN_SEND[sys.argv[1]]["prime"]]))',
         printer],
        cwd=d, capture_output=True, text=True)
    if chk.returncode != 0:
        raise SystemExit(f"hermetic ledger did not import: {chk.stderr[-800:]}")
    left = json.loads(chk.stdout)
    for v in primes:
        if any(sendmod._vec_close(tuple(r), v, sendmod.TOLS['prime']) for r in left):
            raise SystemExit(f"hermetic ledger still proves {v} — the strip did not land")
    if len(left) != len(rows) - len(drop):
        raise SystemExit(f"hermetic ledger: {len(left)} rows left, expected "
                         f"{len(rows) - len(drop)}")
    print(f"hermetic ledger: {os.path.join(d, 'machine.py')}\n"
          f"  {printer} prime rows {len(rows)} -> {len(left)} (dropped {drop or 'none'}), the "
          f"live files' prime {primes[0]} is UNPROVEN there\n"
          f"  the real {os.path.join(CRACKLE, 'machine.py')} is not touched by this suite\n")
    return os.path.join(d, 'send.py')


def run(send_py, path, log, extra=()):
    """One run of the gate, against the hermetic copy. Returns (exit code, stdout).

    Dry run unless a case passes --live, and the only case that does passes no host with it.
    cwd stays the real repo so citation lookups still resolve there; only the three imported gate
    modules come from the copy, because both of them resolve `machine` off __file__.
    """
    r = subprocess.run([sys.executable, send_py, 'send', path, '--log', log, *extra],
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


# name .. note are every case's business; the last three are the one case that needs more than an
# S3 line to be judged, and they default to what the other eight already do.
Case = collections.namedtuple(
    'Case', 'name path want_exit want_s3 want_why want_grants note extra want_out want_hold',
    defaults=((), None, False))


def main():
    tmp = tempfile.mkdtemp(prefix='forced_send_')
    a = gen(tmp, '3.6,4.6')             # the gauge whose whole purpose is to answer a blocked question
    b = gen(tmp, '3.9,4.9')             # a DIFFERENT short file carrying the SAME unproven prime
    lg = gen_long(tmp)                  # same unproven prime, 39 min -- over the ceiling
    send_py = hermetic_ledger(tmp, [a, b, lg])
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
        Case('gauge_first_proof', a, 0, 'FIRST-PROOF', r'inside the 25 min', 1,
             "the gauge that answers a blocked question goes, and the grant is recorded"),
        Case('same_bytes_again', a, 0, 'FIRST-PROOF', r'inside the 25 min', 1,
             "a file holds its OWN grant across re-runs, or every dry run locks out its live send"),
        Case('second_file_same_value', b, 1, 'FAIL', r'already granted to', 1,
             "ONE file per value: a different artifact with the same unproven prime gets no second pass"),
        Case('too_long', lg, 1, 'FAIL', r'past the 25 min', 0,
             "39 min sits in the 25-to-90 gap, where an unproven value gets neither a grant nor a pass"),
        Case('claim_is_not_permission', claim, 1, 'FAIL', r'past the 25 min', 0,
             "the same file declaring itself a coupon is refused for the same reason: duration is the "
             "bound and a header line is not one"),
        Case('validate_refuses', vf, 1, 'FIRST-PROOF', r'inside the 25 min', 0,
             "eligible for rule 6 and still refused -- the send gate never overrules the file gate"),
        Case('s8_self_disclaimed', s8, 1, 'FIRST-PROOF', r'inside the 25 min', 0,
             "a file whose own header disclaims what it claims is refused however short it is"),
        Case('abstain_not_relaxed', ab, 1, 'ABSTAIN', r'NOT MEASURED', 0,
             "UNMEASURED is not UNPROVEN; rule 6 must not hand a grant to a value nothing read"),
        # A USAGE ERROR MUST NOT COST THE GAUGE ITS ONE PASS. This is the file that WOULD be granted
        # -- same bytes as case 1, eligible, S3 FIRST-PROOF -- typed with --live and no host. It
        # regressed for real: the missing-host clause used to run BELOW the grant block, so a typo
        # printed "GRANTED, and SPENT" above a REFUSED verdict and burned the one grant for a value
        # nothing had uploaded. Fixed in 2cfd7dd by deciding the host above the grant.
        #
        # want_out asserts the ORDER, which is the actual fix, not just the outcome: the host
        # refusal must appear BEFORE the grant block, and the grant block must then say NOT GRANTED.
        # want_hold asserts the register is unmoved across the run, which is what "a refused file
        # spends nothing" means -- checked on a FRESH log so a buggy gate would push 0 to 1 rather
        # than being masked by a grant this file already held.
        #
        # NO HOST IS PASSED AND NONE EXISTS IN THIS FILE. send.py's upload sits under
        # `if ok and args.live:`, and this clause has already set ok False, so there is no reachable
        # path to a printer here.
        Case('live_no_host', a, 1, 'FIRST-PROOF', r'inside the 25 min', 0,
             "--live with no --printer-host is REFUSED, and the refusal costs the grant nothing",
             extra=('--live',),
             want_out=r'REFUSED: --live needs an explicit --printer-host[\s\S]*NOT GRANTED',
             want_hold=True),
    ]

    print(f"forcing rule 6 (first proof, ceiling {sendmod.FIRST_PROOF_MAX_MIN:g} min of motion)\n")
    ok_n = 0
    for c in cases:
        # own log per case, EXCEPT the two that deliberately share one to exercise the register
        log = os.path.join(tmp, f'{c.name}.jsonl')
        if c.name == 'same_bytes_again':
            log = os.path.join(tmp, 'gauge_first_proof.jsonl')
        if c.name == 'second_file_same_value':
            log = os.path.join(tmp, 'held.jsonl')
            run(send_py, a, log)                           # the holder takes the grant first
        pre = spent(log)
        code, out = run(send_py, c.path, log, c.extra)
        got_s3, why = s3_line(out)
        got_grants = spent(log)
        why_ok = bool(re.search(c.want_why, why))
        out_ok = bool(re.search(c.want_out, out)) if c.want_out else True
        hold_ok = (got_grants == pre) if c.want_hold else True
        good = (code == c.want_exit and got_s3 == c.want_s3 and why_ok
                and got_grants == c.want_grants and out_ok and hold_ok)
        ok_n += good
        extra_col = ''
        if c.want_out:
            extra_col += f" out={'found' if out_ok else 'MISSING'}"
        if c.want_hold:
            extra_col += f" held={pre}->{got_grants}{'' if hold_ok else ' MOVED'}"
        print(f"{'ok  ' if good else 'FAIL'} {c.name:24s} exit={code}(want {c.want_exit}) "
              f"S3={got_s3}(want {c.want_s3}) reason={'found' if why_ok else 'MISSING'} "
              f"grants={got_grants}(want {c.want_grants}){extra_col}")
        print(f"     {c.note}")
        if not good:
            print(f"       | S3 line: {why.strip()[:400]}")
            print('\n'.join('       | ' + l for l in out.split('\n') if l.strip())[-2000:])

    print(f"\n{ok_n}/{len(cases)} forced cases behave as specified — rule 6 is proven able to "
          f"GRANT, and proven able to decline on duration, on repetition, on a declaration, on "
          f"validate.py, on S8, on abstention and on a --live with no host")
    return 0 if ok_n == len(cases) else 1


if __name__ == '__main__':
    sys.exit(main())
