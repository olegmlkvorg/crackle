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
