#!/bin/sh
# Same as sweep.sh, over the files listed in rest.txt (the first run hit the slot's 3600 s hold).
cd "$(git rev-parse --show-toplevel)" || exit 1
while read -r f; do
  out=$(python3 tools/qa_stl.py "$f" 2>&1)
  p=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +PRINTABLE' | head -1 | awk '{print $1}')
  l=$(printf '%s\n' "$out" | grep -E '^ *(PASS|FAIL) +LAYERSUP' | head -1 | sed 's/  */ /g')
  printf '%s\t%s\t%s\n' "$f" "${p:-none}" "${l:-none}"
done < reports/a1-sweep/rest.txt
