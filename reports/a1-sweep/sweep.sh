#!/bin/sh
# A1 criterion 5 sweep: every tracked STL outside fixtures/, qa_stl closed class, PRINTABLE + LAYERSUP lines.
cd "$(git rev-parse --show-toplevel)" || exit 1
git ls-files '*.stl' | grep -v '^fixtures/' | while read -r f; do
  out=$(timeout 600 python3 tools/qa_stl.py "$f" 2>&1)
  p=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +PRINTABLE' | head -1 | awk '{print $1}')
  l=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +LAYERSUP' | head -1 | sed 's/  */ /g')
  printf '%s\t%s\t%s\n' "$f" "${p:-none}" "${l:-none}"
done
