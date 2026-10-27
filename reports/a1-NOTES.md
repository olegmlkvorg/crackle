# A1 material overhang gate — NOTES (2026-10-27)
Start sha 69a1cc6. LAYERSUP already exists in tools/qa_stl.py (on by default since 85b10a3).
Plan: verify criteria 1-7 against existing code, fill gaps only, run selftest + suite + sweep, mutants.
Next: audit code vs criteria.
- Selftest at 69a1cc6: 28/28 ok (3:40 wall). Criteria 1-4, 7 met by existing code (built 10-24, commits 367717c..85b10a3).
- Fixtures byte-identical to wardrobe-station copies; selftest provenance re-pointed.
- Running: sweep of 88 tracked non-fixture STLs (reports/a1-sweep/), 3 mutants in scratch, then whole suite.
