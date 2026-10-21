#!/usr/bin/env python3
"""BRIDGE-TPU-1 verdict: apply the falsification rule to the result sheet's JSON, mechanically.

Input: the JSON bridge_tpu_results.py's page exports (bridge_tpu1_results.json).
Output: the longest passing span per row, whether design B survives, and, if B is out, the next
question for Oleg. Exit 0 = B survives, 1 = B falsified, 2 = undecided (an 'unclear' decides it),
3 = bad input.

THE RULE, quoted from ~/dev/Assist/reports/toolpath-lattice-verdict-2026-10-18.md:
  line 78: "PASS for a span: sag under 1 lh, the chord does not peel at the post under a hand pull,
            and the bridge above it is clean. The longest passing span becomes the first TPU row of
            the span ledger, per bead."
  line 79: "FALSIFIED (B loses, and the lattice direction is re-opened): in both bead rows, the 7 mm
            span sags over 1 lh or peels at the posts."
  line 82: "The next step is a material or nozzle question for Oleg (PETG, or the 0.8 K2), not a W1
            build."
  line 83: "Also FALSIFIED: posts fail before the bridges do (wobble, fall over, or delaminate at
            20 mm on a 4 mm footprint)."

How the rule is read here, stated because the verdict leaves it open:
  * 'clean' counts toward a span's PASS (line 78) but not toward falsification (line 79 names only
    sag and peel).
  * Line 83 is applied in the same 'both rows' frame as line 79: a row whose posts failed counts
    as a failed row. One failed row leaves B standing on the other row's bead.
  * 'unclear' never counts as pass or fail. If the outcome would change depending on it, the
    verdict is UNDECIDED and names the items to re-check.

Usage: python3 bridge_tpu_verdict.py results.json
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_tpu as bt

KEY_SPAN = "7"
NEXT_Q = "B is out in TPU on the 0.4. Next: PETG, or the 0.8 nozzle on the K2? (verdict line 82)"
VALS = ("pass", "fail", "unclear")


def load(path):
    d = json.load(open(path))
    spans = [f"{g:g}" for g in bt.SPANS]
    for row in bt.ROWS:
        r = d["rows"][row]
        if r["posts"] not in VALS:
            raise ValueError((row, "posts", r["posts"]))
        for s in spans:
            for k in ("sag", "hold", "clean"):
                v = r["spans"][s][k]
                if v not in VALS:
                    raise ValueError((row, s, k, v))
    return d, spans


def row_state(r):
    """'fail', 'ok' or 'unclear' for the falsification test on one row."""
    k = r["spans"][KEY_SPAN]
    if r["posts"] == "fail" or "fail" in (k["sag"], k["hold"]):
        return "fail"
    if r["posts"] == "pass" and k["sag"] == "pass" and k["hold"] == "pass":
        return "ok"
    return "unclear"


def verdict(d, spans):
    lines, unclear, states = [], [], {}
    for row in bt.ROWS:
        r = d["rows"][row]
        passed = [s for s in spans if all(r["spans"][s][k] == "pass" for k in ("sag", "hold", "clean"))]
        best = max(passed, key=float) if passed else None
        gaps = [s for s in spans if best and float(s) < float(best) and s not in passed]
        w, lh = bt.ROWS[row]
        lines.append(f"{row} ({w:g}x{lh:g}): longest passing span "
                     + (f"{best} mm" if best else "none")
                     + (f" (shorter spans not passed: {', '.join(gaps)})" if gaps else ""))
        states[row] = row_state(r)
        if states[row] == "unclear":
            k = r["spans"][KEY_SPAN]
            unclear += [f"{row} posts"] * (r["posts"] == "unclear") + \
                       [f"{row} {KEY_SPAN} mm {q}" for q in ("sag", "hold") if k[q] == "unclear"]
    if all(s == "fail" for s in states.values()):
        lines += ["B: FALSIFIED (7 mm or posts failed in both rows)", NEXT_Q]
        return 1, lines
    if any(s == "ok" for s in states.values()):
        lines.append("B: SURVIVES")
        return 0, lines
    lines.append("B: UNDECIDED. Re-check: " + ", ".join(unclear))
    return 2, lines


def main():
    if len(sys.argv) != 2:
        print(__doc__); return 3
    try:
        d, spans = load(sys.argv[1])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"BAD INPUT: {e!r}"); return 3
    code, lines = verdict(d, spans)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
