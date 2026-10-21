#!/usr/bin/env python3
"""BRIDGE-TPU-1 verdict: fixtures that must each reach their outcome, and a sheet built from the
same model as the page. Each case asserts an exit code AND a line, so a verdict stuck on one
answer fails at least one case.
"""
import copy, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bridge_tpu as bt
import bridge_tpu_results as res

V = os.path.join(ROOT, "bridge_tpu_verdict.py")
SPANS = [f"{g:g}" for g in bt.SPANS]
assert res.model()["spans"] == SPANS, "page and verdict disagree on spans"


def sheet(v="pass"):
    return {"coupon": "BRIDGE-TPU-1", "rows": {r: {"posts": v, "spans": {s: {"sag": v, "hold": v, "clean": v}
            for s in SPANS}} for r in bt.ROWS}}


def run(d):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(d, f)
    r = subprocess.run([sys.executable, V, f.name], capture_output=True, text=True, timeout=60)
    os.unlink(f.name)
    return r.returncode, r.stdout


cases = []
allpass = sheet()
cases.append(("all-pass", allpass, 0, ["R1 (0.6x0.3): longest passing span 16.8 mm", "B: SURVIVES"]))

b_out = sheet()
for r in bt.ROWS:
    b_out["rows"][r]["spans"]["7"]["sag"] = "fail"
    for s in ("10", "13", "16.8"):
        b_out["rows"][r]["spans"][s]["hold"] = "fail"
cases.append(("7mm-fails-both", b_out, 1, ["B: FALSIFIED", "PETG, or the 0.8", "longest passing span 4 mm"]))

mixed = copy.deepcopy(b_out)
mixed["rows"]["R2"]["spans"]["7"]["sag"] = "pass"           # R2 holds 7, still fails 10+
cases.append(("mixed", mixed, 0, ["R2 (0.82x0.42): longest passing span 7 mm", "B: SURVIVES"]))

posts = sheet(); posts["rows"]["R1"]["posts"] = "fail"; posts["rows"]["R2"]["posts"] = "fail"
cases.append(("posts-fail-both", posts, 1, ["B: FALSIFIED"]))

unc = sheet("unclear")
cases.append(("all-unclear", unc, 2, ["B: UNDECIDED", "R1 7 mm sag", "longest passing span none"]))

clean_only = sheet(); [clean_only["rows"][r]["spans"]["7"].update(clean="fail") for r in bt.ROWS]
cases.append(("clean-fail-not-falsifier", clean_only, 0, ["B: SURVIVES", "shorter spans not passed: 7"]))

peel = sheet(); [peel["rows"][r]["spans"]["7"].update(hold="fail") for r in bt.ROWS]
cases.append(("7mm-peels-both", peel, 1, ["B: FALSIFIED"]))

bad = sheet(); bad["rows"]["R1"]["spans"]["4"]["sag"] = "maybe"
cases.append(("bad-value", bad, 3, ["BAD INPUT"]))

n = 0
for name, d, code, needles in cases:
    c, out = run(d)
    assert c == code, (name, c, out)
    for s in needles:
        assert s in out, (name, s, out)
    n += 1
print(f"bridge_tpu_verdict_selftest: {n}/{len(cases)} cases pass")
