# A1 material overhang gate — NOTES (2026-10-27)
Start sha 69a1cc6. LAYERSUP already exists in tools/qa_stl.py (on by default since 85b10a3).
Plan: verify criteria 1-7 against existing code, fill gaps only, run selftest + suite + sweep, mutants.
Next: audit code vs criteria.
- Selftest at 69a1cc6: 28/28 ok (3:40 wall). Criteria 1-4, 7 met by existing code (built 10-24, commits 367717c..85b10a3).
- Fixtures byte-identical to wardrobe-station copies; selftest provenance re-pointed.
- Running: sweep of 88 tracked non-fixture STLs (reports/a1-sweep/), 3 mutants in scratch, then whole suite.

## Results (2026-10-27)
- Whole suite: 17/17 PASS, 0 failed, 0 not run (tests/run_all.py, 141 s). The first run died on ENOSPC
  when the laptop disk filled. This count is from the rerun.
- Mutants run in a scratch copy, each against the selftest. M1 calls every region a bridge: 1 case
  fails (roof-15). M2 makes the allowance 20x: 9 fail. M3 makes the noise floor 1000x: 11 fail. All 3
  are killed.
- Sweep: reports/a1-sweep/README.md. 5 files newly fail, and all are true readings.
- Trashcan policy: the LAYERSUP FAIL stands and the check is not relaxed. There are 27 overhang regions,
  127-142 mm out from the axis at y +-19 and +-60 mm, at z 202.1-202.6 and z 258.5. That is
  the raised name's band, and they are the flat undersides of the letter ribs standing proud of the wall
  (step test, open to air). The fix belongs to gift/emboss.py, which should chamfer the rib undersides
  to 45 deg. Nothing has been printed, so whether these ribs print anyway is still a coupon question.
- Defaults kept: 45 deg angle mode (house rule). Half-line mode is --overhang-deg 0, which the
  selftest proves is looser. Layer height is SLICER_LAYER_H 0.24, the slice the house runs, and the
  verdict is stamped on the line. expected.json's 0.2 mm verdicts all agree at 0.24.
