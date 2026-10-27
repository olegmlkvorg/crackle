# Bridge policy NOTES (2026-10-27)

Brief: ~/dev/Assist/agents/briefs/crackle-bridge-policy-2026-10-27.md
Goal: one place judges bridges. Default direction: LAYERSUP owns bridge judgement for closed parts; PRINTABLE stops
failing downward faces LAYERSUP classifies as a held bridge within --bridge-max.

## Status
- started; reading tools/qa_stl.py PRINTABLE + LAYERSUP and tests next.
- rule built: LAYERSUP is measured before PRINTABLE; PRINTABLE excludes faces whose centroid sits in a
  LAYERSUP bridge region on a plane within one layer of the face (tools/qa_stl.py _bridge_faces).
  No LAYERSUP measurement (--no-layer-support, winding fault) = old PRINTABLE.
- tests/qa_stl_bridge_policy_selftest.py: tunnel block 5 mm passes both, 15 mm fails both and overall;
  mutants excuse-all, excuse-none, overhang-as-bridge all die.
- next: rerun the 10 PRINTABLE-FAIL sweep files, then whole suite.
- resweep of the 10 PRINTABLE-FAIL sweep files (reports/a1-sweep/bridge-policy-resweep.tsv): every
  PRINTABLE and LAYERSUP verdict unchanged; dumbbell_assembled has 34 faces excused, still FAIL.
  The other 78 files are not rerun: excusing faces only lowers PRINTABLE's count, and LAYERSUP's
  classification is untouched, so no PASS can turn FAIL. No file in the sweep failed PRINTABLE alone
  (README: 0 PRINTABLE-FAIL/LAYERSUP-PASS), so the list of files whose only failure was a bridge is empty.
- whole suite: 18/18 passed (heavy slot, 134 s).
- the print-kb hole plate on disk (wardrobe-station 506fd9f0, hole-plate-uncalibrated.stl) still fails:
  LAYERSUP itself reads 32 overhang regions, 310.5 mm2, 0 bridges at z 2.21. That is LAYERSUP's
  classification of the hanging-hole layers, not the PRINTABLE disagreement, and is out of this brief.
