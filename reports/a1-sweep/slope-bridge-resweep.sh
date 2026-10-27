#!/bin/sh
# Slope-bridge resweep (2026-10-27): the sweep's FAIL files only, same columns as sweep.sh.
# Both changes only lower overhang and spanning counts, so only a FAIL can move.
cd "$(git rev-parse --show-toplevel)" || exit 1
cat reports/a1-sweep/sweep-69a1cc6.tsv reports/a1-sweep/sweep-rest-69a1cc6.tsv \
  | awk -F'\t' '$2 ~ /FAIL/ || $3 ~ /FAIL/ {print $1}' | sort -u | while read -r f; do
  out=$(timeout 600 python3 tools/qa_stl.py "$f" 2>&1)
  p=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +PRINTABLE' | head -1 | awk '{print $1}')
  l=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +LAYERSUP' | head -1 | sed 's/  */ /g')
  printf '%s\t%s\t%s\n' "$f" "${p:-none}" "${l:-none}"
done
