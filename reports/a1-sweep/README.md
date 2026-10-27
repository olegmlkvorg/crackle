# A1 criterion 5 sweep, crackle 69a1cc6, 2026-10-27

Every tracked STL outside fixtures/ (88), run through `tools/qa_stl.py` at its defaults (closed class,
LAYERSUP on, 45 deg, 0.24 mm layers, bridge-max 8). There is no STL list in the pre-push gate
(hooks/pre-push only runs tests/run_all.py), so "every STL the gate checks" was taken as every tracked
STL. sweep-69a1cc6.tsv holds 79 files. The heavy slot killed the run at its 3600 s hold, and
sweep-rest-69a1cc6.tsv holds the other 9 (rest.txt). Columns: file, PRINTABLE, LAYERSUP line.

Totals: 73 PASS/PASS, 10 FAIL/FAIL, 5 PRINTABLE-PASS/LAYERSUP-FAIL, 0 PRINTABLE-FAIL/LAYERSUP-PASS.

The newly failing files, each judged by hand:
- fabric/chainmail_link.stl: the tilted-ring crest. This is criterion 5's wanted FAIL. Its class is fabric,
  where LAYERSUP does not run.
- fabric/chainmail_coupon.stl: the same rings tiled. It is a fabric-class part with the same real crest
  overhang, and LAYERSUP does not run on it in its own class.
- marble/sort_head_gate_v1.stl and _seat0 (byte-identical): a real 40 deg-from-horizontal vase flare,
  judged in reports/layersup-judgement-2026-10-24.md. Both already fail WATERTIGHT, so the overall verdict
  is unchanged.
- gift/trashcan.stl: see the trashcan policy in reports/a1-NOTES.md.
